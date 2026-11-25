"""Interpretation layer: turn a parsed SpecIR into something a human can review fast.

Two engines:
- heuristic: offline, deterministic, no API key. Good for CI and for trying the tool.
- llm: any LiteLLM-supported model (Claude, OpenAI, Ollama...). Every claim must cite
  file:line; citations that do not exist in the documents are dropped.
"""

from __future__ import annotations

import json
import re
from collections import Counter

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


class _Cite(BaseModel):
    file: str
    line: int


class _Decision(BaseModel):
    title: str
    choice: str
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)
    risk: str = ""
    attention: Attention
    sources: list[_Cite]


class _Risk(BaseModel):
    title: str
    impact: str = ""
    mitigation: str = ""
    severity: str = "medium"
    sources: list[_Cite]


class _Question(BaseModel):
    question: str
    why_it_matters: str = ""
    sources: list[_Cite]


class LLMInsights(BaseModel):
    one_liner: str
    bullets: list[str]
    you_must_decide: list[str]
    decisions: list[_Decision]
    risks: list[_Risk]
    questions: list[_Question]


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


def _resolve(cites: list[_Cite], docs: dict[str, str]) -> list[SourceRef]:
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


def llm_insights(ir: SpecIR, model: str = DEFAULT_MODEL, lang: str | None = None) -> SpecIR:
    try:
        import litellm
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('LLM mode needs the extra: pip install "unboringspec[llm]"') from e

    lang_rule = f", but write the output in {lang}" if lang else ""
    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(lang_rule=lang_rule)},
            {"role": "user", "content": _numbered(ir.documents)},
        ],
        response_format=LLMInsights,
        temperature=0.2,
    )
    data = _parse_json(resp.choices[0].message.content)
    docs = ir.documents

    ir.summary = Summary(one_liner=data.one_liner, bullets=data.bullets, you_must_decide=data.you_must_decide)

    # Keep the deterministic plan.md tech-context entries; replace interpretive decisions.
    kept = [d for d in ir.decisions if d.id.startswith("TC")]
    llm_decisions = [
        Decision(
            id=f"D{i}",
            title=d.title,
            choice=d.choice,
            rationale=d.rationale,
            alternatives=d.alternatives,
            risk=d.risk,
            attention=d.attention,
            sources=_resolve(d.sources, docs),
        )
        for i, d in enumerate(data.decisions, start=1)
    ]
    ir.decisions = [d for d in llm_decisions if d.sources] + kept

    ir.risks = [
        Risk(
            id=f"R{i}",
            title=r.title,
            impact=r.impact,
            mitigation=r.mitigation,
            severity=r.severity if r.severity in {"low", "medium", "high"} else "medium",
            sources=_resolve(r.sources, docs),
        )
        for i, r in enumerate(data.risks, start=1)
    ]
    ir.risks = [r for r in ir.risks if r.sources]

    # Explicit [NEEDS CLARIFICATION] markers always stay; LLM questions are added after.
    llm_qs = [
        OpenQuestion(id="", question=q.question, why_it_matters=q.why_it_matters, sources=_resolve(q.sources, docs))
        for q in data.questions
    ]
    ir.questions = ir.questions + [q for q in llm_qs if q.sources]
    for i, q in enumerate(ir.questions, start=1):
        q.id = f"Q{i}"

    ir.generated_by = f"llm:{model}"
    return ir
