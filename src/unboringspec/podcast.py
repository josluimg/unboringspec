"""Spec podcast: two hosts talk through the spec so a reviewer can listen instead of read.

Same pattern as the review: the agent (or an API model) writes a script that follows a
published contract, and the CLI validates it and turns it into audio. Host A guides the
listener through the spec; host B is the skeptic who pushes on decisions and gaps. The
skeptic is what makes this a review and not a summary read aloud.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .insights import Citation, _numbered, _parse_json_as, _resolve
from .ir import SourceRef, SpecIR

PODCAST_SCHEMA_VERSION = 1
PODCAST_SCHEMA_ID = (
    "https://raw.githubusercontent.com/josluimg/unboringspec/main/schemas/"
    f"podcast.v{PODCAST_SCHEMA_VERSION}.schema.json"
)


class Host(BaseModel):
    """One of the two voices."""

    id: Literal["A", "B"]
    name: str = Field(description="A first name that sounds natural in the script language.")
    role: Literal["guide", "skeptic"] = Field(
        description="'guide' explains the spec with enthusiasm; 'skeptic' challenges decisions and gaps."
    )


class Turn(BaseModel):
    """One spoken turn. Written for the ear: no Markdown, no lists, no file paths, no IDs like FR-006."""

    speaker: Literal["A", "B"]
    text: str = Field(description="What the host says, 1 to 3 short sentences.")
    sources: list[Citation] = Field(
        default_factory=list, description="Optional citations for the claim in this turn (shown in the transcript)."
    )


class PodcastScript(BaseModel):
    """unboringspec podcast script: a two-host conversation about one spec."""

    title: str = Field(description="Episode title, max 10 words.")
    language: str = Field(description="BCP 47 language code of the script, e.g. 'es' or 'en'.")
    hosts: list[Host] = Field(description="Exactly two hosts: A (guide) and B (skeptic).")
    turns: list[Turn] = Field(description="The conversation in order. Aim for 900 to 1200 words in total.")


def podcast_json_schema() -> dict:
    schema = PodcastScript.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PODCAST_SCHEMA_ID,
        "title": f"unboringspec podcast script v{PODCAST_SCHEMA_VERSION}",
        **{k: v for k, v in schema.items() if k != "title"},
    }


PODCAST_PROMPT = """You write the script of a short podcast episode that helps a software engineer review a
Spec-Driven Development spec by listening instead of reading.

Two hosts:
- Host A, the guide: explains what is being built and why, clearly and with some enthusiasm.
- Host B, the skeptic: friendly but sharp. Pushes on risky decisions, gaps, contradictions and
  anything marked as unresolved. Asks "what happens if...", "who decided that...", "is that enough?".
They are colleagues having a real conversation, not reading a document. They interrupt, agree,
disagree, use short sentences and plain words.

Structure:
1. Hook (1 or 2 turns): the one thing that makes this spec interesting or risky.
2. What it is: the feature and who it is for, in plain words.
3. Two to four key decisions, debated: the guide explains, the skeptic challenges, they land somewhere.
4. What the listener must decide: the open questions, said plainly, one by one.
5. Close: the guide sums up in three short points what the reviewer should do next.

Rules:
- Language: {lang_rule}. Choose host names that sound natural in that language.
- 900 to 1200 words in total (about 6 to 8 minutes). Turns of 1 to 3 sentences.
- Written for the ear: no Markdown, no bullet lists, no emojis, no URLs, no file paths, no requirement IDs
  like FR-006 or T012. Say "the requirement about GPS data" instead. Spell out symbols.
- Do not invent facts that are not in the documents. Opinions and questions are welcome.
- When a turn states a fact from the spec, add a citation (file + line number from the numbered documents).
"""


def build_podcast_prompt(ir: SpecIR, insights_json: str | None = None, lang: str | None = None) -> str:
    lang_rule = f"write in {lang}" if lang else "the same language as the spec"
    parts = [PODCAST_PROMPT.format(lang_rule=lang_rule)]
    parts.append(
        "## Output\n\nWrite ONLY a JSON object that validates against this JSON Schema. "
        "No prose, no Markdown fences.\n\n```json\n"
        + json.dumps(podcast_json_schema(), separators=(",", ":"))
        + "\n```"
    )
    if insights_json:
        parts.append(
            "## Review analysis already done\n\nUse it to choose what to talk about. "
            "Items with attention 'decide' and the open questions matter most.\n\n```json\n"
            + insights_json.strip()
            + "\n```"
        )
    parts.append("## Documents\n\n" + _numbered(ir.documents))
    return "\n\n".join(parts)


def parse_script(content: str) -> PodcastScript:
    return _parse_json_as(PodcastScript, content)


class ResolvedTurn(BaseModel):
    speaker: Literal["A", "B"]
    name: str
    role: str
    text: str
    sources: list[SourceRef] = Field(default_factory=list)


def validate_script(script: PodcastScript, docs: dict[str, str]) -> tuple[list[ResolvedTurn], list[str]]:
    """Return speakable turns and a list of problems. Problems with the cast are fatal (raise);
    invalid citations are dropped and reported."""
    hosts = {h.id: h for h in script.hosts}
    if set(hosts) != {"A", "B"} or {h.role for h in script.hosts} != {"guide", "skeptic"}:
        raise ValueError("The script needs exactly two hosts: A and B, one 'guide' and one 'skeptic'.")
    problems: list[str] = []
    turns: list[ResolvedTurn] = []
    for i, t in enumerate(script.turns, start=1):
        text = " ".join(t.text.split())
        if not text:
            problems.append(f"turn {i} is empty and was skipped")
            continue
        refs = _resolve(t.sources, docs)
        if len(refs) < len(t.sources):
            problems.append(f"turn {i}: {len(t.sources) - len(refs)} citation(s) point to lines that do not exist")
        h = hosts[t.speaker]
        turns.append(ResolvedTurn(speaker=t.speaker, name=h.name, role=h.role, text=text, sources=refs))
    if not turns:
        raise ValueError("The script has no turns to speak.")
    return turns, problems


def word_count(turns: list[ResolvedTurn]) -> int:
    return sum(len(t.text.split()) for t in turns)


def transcript_markdown(script: PodcastScript, turns: list[ResolvedTurn]) -> str:
    lines = [f"# {script.title}", ""]
    for t in turns:
        cites = " ".join(f"`{s.file}:{s.line}`" for s in t.sources)
        lines.append(f"**{t.name}:** {t.text}" + (f" {cites}" if cites else ""))
        lines.append("")
    return "\n".join(lines)
