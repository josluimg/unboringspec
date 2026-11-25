"""Interpretation layer: turn a parsed SpecIR into something a human can review fast.

Three modes share one contract (`build_prompt` -> `LLMInsights` JSON -> `apply_insights`):
- agent: the coding agent the user already runs (Claude Code, Copilot, Codex...) reads the
  prompt and writes the JSON. No API key.
- api: LiteLLM calls a model directly (Claude, OpenAI, Ollama...). For CI.
- heuristic: offline and deterministic, for a quick try and for tests.

Every claim must cite file:line; citations that do not exist in the documents are dropped.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .ir import Attention, Decision, OpenQuestion, Risk, SourceRef, SpecIR, Summary

DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"


# --- heuristic -------------------------------------------------------------------


def heuristic_insights(ir: SpecIR) -> SpecIR:
    bullets: list[str] = []
    if ir.stories:
        prio = Counter(s.priority or "unprioritised" for s in ir.stories)
        bullets.append(
            f"{len(ir.stories)} user stories ("
            + ", ".join(f"{k}: {v}" for k, v in sorted(prio.items()))
            + ")"
        )
    if ir.requirements:
        bullets.append(f"{len(ir.requirements)} requirements")
    if ir.tasks:
        par = sum(t.parallel for t in ir.tasks)
        done = sum(t.done for t in ir.tasks)
        bullets.append(f"{len(ir.tasks)} tasks, {par} parallelisable, {done} done")
    if ir.decisions:
        bullets.append(f"{len(ir.decisions)} technical decisions recorded")
    bullets.append(f"{len(ir.documents)} documents, {sum(len(t.splitlines()) for t in ir.documents.values())} lines total")

    must = [q.question for q in ir.questions]
    must += [f"{d.title}: {d.choice}" for d in ir.decisions_by_attention(Attention.decide)]

    ir.summary = Summary(
        one_liner=ir.description or ir.feature,
        bullets=bullets,
        you_must_decide=must,
    )
    ir.generated_by = "heuristic"
    return ir


# --- llm -------------------------------------------------------------------------


# The contract every agent (or API model) must return. It is published as
# schemas/insights.v{SCHEMA_VERSION}.schema.json; tests keep both in sync.
# Bump SCHEMA_VERSION on breaking changes (removed or renamed fields, new required fields).
SCHEMA_VERSION = 1
SCHEMA_ID = f"https://raw.githubusercontent.com/josluimg/unboringspec/main/schemas/insights.v{SCHEMA_VERSION}.schema.json"


# Rules the schema publishes but parsing does not enforce: one bad item should be dropped
# with a warning (see apply_insights), not fail the whole review.
_AT_LEAST_ONE = {"minItems": 1}


class Citation(BaseModel):
    """A pointer to the exact line in the spec documents that supports a claim."""

    file: str = Field(description="Document path exactly as shown in the '===== FILE: <path> =====' header.")
    line: int = Field(
        description="1-based line number as shown in the numbered document.", json_schema_extra={"minimum": 1}
    )


class DecisionInsight(BaseModel):
    """A meaningful choice the spec makes (architecture, scope, data, UX, trade-off)."""

    title: str = Field(description="Short name of the decision.")
    choice: str = Field(description="What was decided, in one sentence.")
    rationale: str = Field("", description="Why, as stated or implied by the spec.")
    alternatives: list[str] = Field(default_factory=list, description="Options considered and not chosen.")
    risk: str = Field("", description="What could go wrong with this choice. Empty if nothing notable.")
    attention: Attention = Field(
        description="'decide': unresolved, ambiguous or high-risk, needs a human call. "
        "'review': a reasonable person could disagree. 'routine': conventional."
    )
    sources: list[Citation] = Field(description="At least one real citation.", json_schema_extra=_AT_LEAST_ONE)


class RiskInsight(BaseModel):
    """A delivery or product risk, including ones the spec implies but does not name."""

    title: str
    impact: str = Field("", description="What happens if the risk materialises.")
    mitigation: str = Field("", description="A concrete way to reduce it.")
    severity: Literal["low", "medium", "high"] = "medium"
    sources: list[Citation] = Field(json_schema_extra=_AT_LEAST_ONE)


class QuestionInsight(BaseModel):
    """A gap, contradiction or missing edge case a careful reviewer would raise."""

    question: str
    why_it_matters: str = Field("", description="One sentence on the consequence of leaving it open.")
    sources: list[Citation] = Field(json_schema_extra=_AT_LEAST_ONE)


class LLMInsights(BaseModel):
    """unboringspec insights: what a human reviewer needs from a spec, with every claim cited."""

    one_liner: str = Field(description="What is being built and for whom, max 25 words.")
    bullets: list[str] = Field(
        description="Up to 5 things a reviewer must know, max 20 words each.", json_schema_extra={"maxItems": 5}
    )
    you_must_decide: list[str] = Field(description="Only items that genuinely need a human call. May be empty.")
    decisions: list[DecisionInsight]
    risks: list[RiskInsight]
    questions: list[QuestionInsight]


def json_schema() -> dict:
    """The published JSON Schema of the contract."""
    schema = LLMInsights.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": f"unboringspec insights v{SCHEMA_VERSION}",
        **{k: v for k, v in schema.items() if k != "title"},
    }


SYSTEM_PROMPT = """You help a software engineer review a Spec-Driven Development spec without reading all of it.
Your job is to direct human attention, not to summarise evenly.

Rules:
- Write in the same language as the spec{lang_rule}.
- one_liner: what is being built and for whom, max 25 words.
- bullets: at most 5, each max 20 words, the things a reviewer must know.
- you_must_decide: only items that genuinely need a human call. Empty is fine.
- decisions: the meaningful choices in the spec (architecture, scope, data, UX, trade-offs).
  attention = "decide" if unresolved, ambiguous or high-risk; "review" if a reasonable person could disagree;
  "routine" if conventional.
- risks: real delivery or product risks, including ones the spec does not mention but implies.
- questions: gaps, contradictions or missing edge cases a careful reviewer would raise.
- Every decision, risk and question MUST cite at least one source as file + line number from the
  numbered documents below. Never invent citations. If you cannot cite it, leave it out.
"""


def _numbered(docs: dict[str, str]) -> str:
    parts = []
    for name, text in docs.items():
        numbered = "\n".join(f"{i:>4}| {line}" for i, line in enumerate(text.splitlines(), start=1))
        parts.append(f"===== FILE: {name} =====\n{numbered}")
    return "\n\n".join(parts)


def _resolve(cites: list[Citation], docs: dict[str, str]) -> list[SourceRef]:
    out = []
    for c in cites:
        lines = docs.get(c.file, "").splitlines()
        if 1 <= c.line <= len(lines):
            out.append(SourceRef(file=c.file, line=c.line, excerpt=lines[c.line - 1].strip()[:240]))
    return out


def _parse_json(content: str) -> LLMInsights:
    try:
        return LLMInsights.model_validate_json(content)
    except ValidationError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise
        return LLMInsights.model_validate(json.loads(match.group(0)))


def parse_insights(content: str) -> LLMInsights:
    """Parse insights JSON written by an agent or returned by an API. Tolerates code fences."""
    return _parse_json(content)


# --- the contract shared by agent mode and API mode ---------------------------------


def compact_schema() -> str:
    """JSON Schema without pydantic's auto-generated titles: same contract, far fewer tokens."""

    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if not (k == "title" and isinstance(v, str))}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return json.dumps(strip(json_schema()), separators=(",", ":"))


def build_prompt(ir: SpecIR, lang: str | None = None, *, for_agent: bool = False) -> str:
    """The full prompt: instructions, JSON schema and the line-numbered documents.

    In agent mode (Copilot, Claude Code, Codex...) the host agent reads this file and writes
    insights.json itself, so no API key is needed.
    """
    lang_rule = f", but write the output in {lang}" if lang else ""
    parts = [SYSTEM_PROMPT.format(lang_rule=lang_rule)]
    if for_agent:
        parts.append(
            "## Output\n\nWrite ONLY a JSON object that validates against this JSON Schema. "
            "No prose, no Markdown fences.\n\n```json\n" + compact_schema() + "\n```"
        )
    parts.append("## Documents\n\n" + _numbered(ir.documents))
    return "\n\n".join(parts)


def apply_insights(ir: SpecIR, data: LLMInsights, generated_by: str) -> tuple[SpecIR, int]:
    """Merge LLM insights into the IR. Returns the IR and how many items were dropped
    because none of their citations exist in the documents."""
    docs = ir.documents
    dropped = 0

    ir.summary = Summary(one_liner=data.one_liner, bullets=data.bullets[:5], you_must_decide=data.you_must_decide)

    # Keep the deterministic plan.md tech-context entries; replace interpretive decisions.
    kept = [d for d in ir.decisions if d.id.startswith("TC")]
    decisions = []
    for d in data.decisions:
        sources = _resolve(d.sources, docs)
        if not sources:
            dropped += 1
            continue
        decisions.append(
            Decision(
                id=f"D{len(decisions) + 1}",
                title=d.title,
                choice=d.choice,
                rationale=d.rationale,
                alternatives=d.alternatives,
                risk=d.risk,
                attention=d.attention,
                sources=sources,
            )
        )
    ir.decisions = decisions + kept

    risks = []
    for r in data.risks:
        sources = _resolve(r.sources, docs)
        if not sources:
            dropped += 1
            continue
        risks.append(
            Risk(
                id=f"R{len(risks) + 1}",
                title=r.title,
                impact=r.impact,
                mitigation=r.mitigation,
                severity=r.severity,
                sources=sources,
            )
        )
    ir.risks = risks

    # Explicit [NEEDS CLARIFICATION] markers always stay; LLM questions are added after.
    for q in data.questions:
        sources = _resolve(q.sources, docs)
        if not sources:
            dropped += 1
            continue
        ir.questions.append(OpenQuestion(id="", question=q.question, why_it_matters=q.why_it_matters, sources=sources))
    for i, q in enumerate(ir.questions, start=1):
        q.id = f"Q{i}"

    ir.generated_by = generated_by
    return ir, dropped


def llm_insights(ir: SpecIR, model: str = DEFAULT_MODEL, lang: str | None = None) -> tuple[SpecIR, int]:
    """API mode: call the model directly through LiteLLM (needs a provider API key)."""
    try:
        import litellm
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('API mode needs the extra: pip install "unboringspec[llm]"') from e

    instructions, _, documents = build_prompt(ir, lang).partition("## Documents\n\n")
    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": documents},
        ],
        response_format=LLMInsights,
        temperature=0.2,
    )
    data = _parse_json(resp.choices[0].message.content)
    return apply_insights(ir, data, f"api:{model}")
