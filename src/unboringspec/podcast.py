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


# The parts every episode follows (#4). The first turn of each part carries its id, so the player can
# jump to it, the most useful jump being straight to what the listener must decide.
CHAPTERS = ("hook", "overview", "decisions", "to_decide", "close")
Chapter = Literal["hook", "overview", "decisions", "to_decide", "close"]


class Turn(BaseModel):
    """One spoken turn. Written for the ear: no Markdown, no lists, no file paths, no IDs like FR-006."""

    speaker: Literal["A", "B"]
    text: str = Field(description="What the host says, 1 to 3 short sentences.")
    sources: list[Citation] = Field(
        default_factory=list, description="Optional citations for the claim in this turn (shown in the transcript)."
    )
    chapter: Chapter | None = Field(
        None,
        description="Only on the first turn of each part of the episode: 'hook', 'overview' (what it is), "
        "'decisions' (the key decisions), 'to_decide' (what the listener must decide), 'close'.",
    )


class Term(BaseModel):
    """A word the voices must say in another language: a product name or team jargon."""

    text: str = Field(max_length=60, description="The word or name exactly as written in the turns, e.g. 'Snowflake'.")
    lang: str = Field(description="BCP 47 code of the language it is pronounced in, e.g. 'en'.")


class PodcastScript(BaseModel):
    """unboringspec podcast script: a two-host conversation about one spec."""

    title: str = Field(description="Episode title, max 10 words.")
    language: str = Field(description="BCP 47 language code of the script, e.g. 'es' or 'en'.")
    tone: str = Field("", description="The tone the episode was written in: a preset id (e.g. 'roast') or 'custom'.")
    hosts: list[Host] = Field(description="Exactly two hosts: A (guide) and B (skeptic).")
    turns: list[Turn] = Field(description="The conversation in order. Aim for 900 to 1200 words in total.")
    terms: list[Term] = Field(
        default_factory=list,
        max_length=80,
        description="Words in the turns that are pronounced in another language than the script's: product "
        "names and technical jargon the team says in English. Natural voices say them in that language.",
    )


def podcast_json_schema() -> dict:
    schema = PodcastScript.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PODCAST_SCHEMA_ID,
        "title": f"unboringspec podcast script v{PODCAST_SCHEMA_VERSION}",
        **{k: v for k, v in schema.items() if k != "title"},
    }


class Tone(BaseModel):
    id: str
    label: str
    summary: str  # one line for `unboring podcast tones`
    style: str  # instructions for the script writer, in English (the script language is set separately)
    pace: float = 1.0  # relative to BASE_SPEED: above 1 faster (sports), below 1 slower (noir)

    @property
    def speed(self) -> float:
        return round(BASE_SPEED * self.pace, 2)


# Natural voices sound slow at 1.0, so episodes are recorded a little faster by default (#57);
# each tone's pace is relative to this, and --speed overrides the result.
BASE_SPEED = 1.2


TONES: dict[str, Tone] = {
    t.id: t
    for t in [
        Tone(
            id="casual",
            label="Casual",
            summary="Two colleagues over coffee. The default.",
            style="Two colleagues chatting over coffee. Relaxed and natural, a little humour, plain words. "
            "They interrupt, agree and disagree.",
        ),
        Tone(
            id="formal",
            label="Formal",
            summary="A measured briefing, like an architecture review board.",
            style="A professional briefing, like a presentation to an architecture review board. Measured, "
            "precise language. No slang and no jokes. The skeptic is polite but rigorous and asks for evidence.",
        ),
        Tone(
            id="bro",
            label="Bro",
            summary="Close friends, heavy slang and banter (tío, illo, bro, no cap...).",
            style="Two close friends talking with heavy colloquial slang that is typical of the script language "
            "(in Spanish things like 'tío', 'illo', 'en plan', 'qué fuerte', 'flipar'; in English things like "
            "'bro', 'no cap', 'lowkey', 'that's wild'). Banter, exaggeration and running jokes. "
            "The slang is in the delivery; every fact about the spec is still exact.",
            pace=1.05,
        ),
        Tone(
            id="roast",
            label="Roast",
            summary="A comedy roast of the spec. No mercy, all of it true.",
            style="A comedy roast of the spec, and the skeptic does not hold back: sarcasm, punchlines, "
            "exaggerated disbelief at every risky decision and every unanswered question. The guide defends "
            "the spec with comebacks and concedes when a hit lands. Roast the spec and its decisions, never "
            "real people, teams or the authors. Under every joke there must be a real, cited issue: the "
            "listener should finish laughing and knowing exactly what to fix.",
            pace=1.05,
        ),
        Tone(
            id="sports",
            label="Sports commentary",
            summary="Live play-by-play, like two football commentators.",
            style="Live sports commentary, like two football commentators narrating a match. The spec is the "
            "game, decisions are plays, risks are fouls, open questions are penalties still to be called. "
            "Excited, fast, with commentator catchphrases and replays of the key moments.",
            pace=1.1,
        ),
        Tone(
            id="noir",
            label="Detective noir",
            summary="A hard-boiled detective investigates the spec.",
            style="A hard-boiled detective story. The guide narrates in first person as a detective investigating "
            "the spec; the skeptic is the partner who doubts every lead. Rainy-night atmosphere and short, "
            "dramatic sentences, but every clue is a real fact from the documents, and the open questions are "
            "the unsolved part of the case.",
            pace=0.95,
        ),
        Tone(
            id="eli5",
            label="For non-technical listeners",
            summary="No jargon: for product, business or anyone outside engineering.",
            style="For listeners outside engineering (product, business, leadership). No jargon at all: every "
            "technical idea is explained with an everyday analogy. The skeptic asks what a manager would ask: "
            "cost, risk for users, what happens if we get it wrong.",
        ),
    ]
}
DEFAULT_TONE = "casual"
MAX_CUSTOM_TONE = 300


def resolve_tone(tone: str | None) -> tuple[str, str, float]:
    """Return (id, style instructions, default speed) for a preset id or a custom description."""
    tone = (tone or DEFAULT_TONE).strip()
    if tone.lower() in TONES:
        t = TONES[tone.lower()]
        return t.id, t.style, t.speed
    if len(tone) > MAX_CUSTOM_TONE:
        raise ValueError(f"A custom tone must be at most {MAX_CUSTOM_TONE} characters.")
    return "custom", f"Custom style requested by the listener: {tone}", BASE_SPEED


def tone_speed(tone_id: str) -> float:
    return TONES[tone_id].speed if tone_id in TONES else BASE_SPEED


PODCAST_PROMPT = """You write the script of a short podcast episode that helps a software engineer review a
Spec-Driven Development spec by listening instead of reading.

Two hosts:
- Host A, the guide: explains what is being built and why, clearly and with some enthusiasm.
- Host B, the skeptic: friendly but sharp. Pushes on risky decisions, gaps, contradictions and
  anything marked as unresolved. Asks "what happens if...", "who decided that...", "is that enough?".
It is a real conversation, not two people reading a document.

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
- Whatever the tone: the facts stay exact, the open questions are all mentioned, and nobody real is mocked.
- Say things the way the team says them. Keep technical jargon that the team uses in English as it is
  (endpoint, deadline, backoffice, commit, pull request...): do not translate it. Words that are not jargon go
  in the script language: in particular, never say "spec" outside English; say the word for specification
  (Spanish: "la especificación"; French: "la spécification"; Portuguese: "a especificação";
  Italian: "la specifica"; German: "die Spezifikation").
- List in "terms" every word in the turns that is pronounced in another language than the script's: product
  and company names (Snowflake, Control-M, PostgreSQL) and the English jargon you kept. Each once, written
  exactly as in the turns, with the language it is pronounced in ("en"). Natural voices then say them right.
- Set "tone" in the output to "{tone_id}".
- Mark the first turn of each part of the structure with "chapter": "hook", "overview" (what it is),
  "decisions", "to_decide" (what the listener must decide) and "close", in that order. Listeners use them
  to jump, above all straight to what they must decide.

## Tone

{tone_style}
"""


def build_podcast_prompt(
    ir: SpecIR, insights_json: str | None = None, lang: str | None = None, tone: str | None = None
) -> str:
    lang_rule = f"write in {lang}" if lang else "the same language as the spec"
    tone_id, tone_style, _ = resolve_tone(tone)
    parts = [PODCAST_PROMPT.format(lang_rule=lang_rule, tone_id=tone_id, tone_style=tone_style)]
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
    chapter: str | None = None


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
        turns.append(ResolvedTurn(speaker=t.speaker, name=h.name, role=h.role, text=text, sources=refs, chapter=t.chapter))
    if not turns:
        raise ValueError("The script has no turns to speak.")
    return turns, problems


def chapter_marks(turns: list[ResolvedTurn], seconds: list[float], pause_ms: int) -> list[dict]:
    """Start and end, in seconds, of each chapter, from the recorded length of every turn.

    A chapter starts where the first turn marked with it starts; it ends where the next one starts,
    or with the episode. A chapter marked twice keeps its first mark.
    """
    starts: dict[str, float] = {}
    at = 0.0
    for i, (turn, length) in enumerate(zip(turns, seconds)):
        if turn.chapter and turn.chapter not in starts:
            starts[turn.chapter] = round(at, 2)
        at += length + (pause_ms / 1000 if i < len(turns) - 1 else 0)
    total = round(at, 2)
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    return [
        {"id": cid, "start": start, "end": ordered[i + 1][1] if i + 1 < len(ordered) else total}
        for i, (cid, start) in enumerate(ordered)
    ]


def record_episode(engine, script: PodcastScript, turns: list[ResolvedTurn], voices: dict, speed: float,
                   out_stem, progress=None) -> tuple:
    """Voice every turn, measure where each chapter starts, and assemble the episode.

    Returns (audio path, length in seconds, chapters). `progress(i, total, turn)` is called before
    each turn. Engine errors propagate (EngineUnavailable).
    """
    import tempfile
    from pathlib import Path

    from .i18n import table
    from .tts import PAUSE_MS, assemble, wav_seconds

    terms = [(term.text, term.lang) for term in script.terms]
    out_stem = Path(out_stem)
    with tempfile.TemporaryDirectory(prefix="unboring-") as tmp:
        parts = []
        for i, t in enumerate(turns, start=1):
            if progress:
                progress(i, len(turns), t)
            part = Path(tmp) / f"{i:04d}.wav"
            engine.synth(t.text, voices[t.role], script.language, speed, part, terms=terms)
            parts.append(part)
        lengths = [wav_seconds(p) for p in parts]
        chapters = chapter_marks(turns, lengths, PAUSE_MS)
        labels = table(script.language)
        for old in (out_stem.with_suffix(".mp3"), out_stem.with_suffix(".wav")):
            old.unlink(missing_ok=True)
        audio = assemble(
            parts, out_stem, pause_ms=PAUSE_MS,
            chapters=[(labels[f"chapter_{c['id']}"], c["start"], c["end"]) for c in chapters],
        )
    seconds = sum(lengths) + PAUSE_MS / 1000 * (len(parts) - 1)
    return audio, seconds, chapters


def word_count(turns: list[ResolvedTurn]) -> int:
    return sum(len(t.text.split()) for t in turns)


def transcript_markdown(script: PodcastScript, turns: list[ResolvedTurn]) -> str:
    from .i18n import table

    labels = table(script.language)
    lines = [f"# {script.title}", ""]
    for t in turns:
        if t.chapter:
            lines += [f"## {labels[f'chapter_{t.chapter}']}", ""]
        cites = " ".join(f"`{s.file}:{s.line}`" for s in t.sources)
        lines.append(f"**{t.name}:** {t.text}" + (f" {cites}" if cites else ""))
        lines.append("")
    return "\n".join(lines)
