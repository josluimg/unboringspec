"""Render a SpecIR into a single self-contained HTML review page."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jinja2 import Environment, PackageLoader

from . import __version__
from .diagrams import spec_diagrams
from .diff import _norm, areas, summarize
from .ir import Attention, SpecIR


def find_podcast(folder: Path, docs: dict[str, str]) -> dict | None:
    """If a rendered podcast sits next to the page, embed a player and the transcript."""
    from .podcast import parse_script, validate_script

    audio = next((folder / n for n in ("podcast.mp3", "podcast.wav") if (folder / n).exists()), None)
    script = folder / "podcast.json"
    if not audio or not script.exists():
        return None
    try:
        parsed = parse_script(script.read_text(encoding="utf-8"))
        turns, _ = validate_script(parsed, docs)
    except Exception:
        return None
    from .podcast import TONES

    tone = TONES[parsed.tone].label if parsed.tone in TONES else ("Custom tone" if parsed.tone else "")
    return {"audio": audio.name, "title": parsed.title, "tone": tone, "turns": turns}


def review_keys(ir: SpecIR) -> dict[str, str]:
    """A key per decision and question that follows the item's identity, not its position.

    Positional ids (D1, Q2...) are reassigned on every render, so marks saved under them
    landed on other items after the spec changed (#29). The key covers what the reader saw
    (title and content) and the cited file, but not the line number, which shifts when
    unrelated lines move. A changed item gets a new key, so its old mark does not apply.
    """
    keys: dict[str, str] = {}
    seen: dict[str, int] = {}
    items = [("d", d.id, f"{_norm(d.title)}|{_norm(d.choice)}", d.sources) for d in ir.decisions]
    items += [("q", q.id, _norm(q.question), q.sources) for q in ir.questions]
    for kind, item_id, text, sources in items:
        file = sources[0].file if sources else ""
        digest = hashlib.sha1(f"{kind}|{text}|{file}".encode("utf-8")).hexdigest()[:12]
        n = seen.get(digest, 0)
        seen[digest] = n + 1
        keys[item_id] = f"{kind}-{digest}" + (f"-{n}" if n else "")  # identical twins stay distinct
    return keys


def render_html(ir: SpecIR, podcast: dict | None = None) -> str:
    env = Environment(loader=PackageLoader("unboringspec", "templates"), autoescape=True)
    tpl = env.get_template("review.html.j2")

    stories = {s.id: s for s in ir.stories}
    tasks_by_story: dict[str, list] = {}
    for t in ir.tasks:
        tasks_by_story.setdefault(t.story or "Shared", []).append(t)

    # Embedded as JSON for the source drawer and the review export. Escape "</" so a spec
    # containing "</script>" cannot break out of the script tag.
    keys = review_keys(ir)
    payload = json.dumps(
        {
            "feature": ir.feature,
            "documents": ir.documents,
            "decisions": [{"id": d.id, "key": keys[d.id], "title": d.title, "choice": d.choice} for d in ir.decisions],
            "questions": [{"id": q.id, "key": keys[q.id], "question": q.question} for q in ir.questions],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return tpl.render(
        ir=ir,
        version=__version__,
        decide=ir.decisions_by_attention(Attention.decide),
        review=ir.decisions_by_attention(Attention.review),
        routine=ir.decisions_by_attention(Attention.routine),
        stories=stories,
        tasks_by_story=tasks_by_story,
        payload=payload,
        keys=keys,
        podcast=podcast,
        # From understanding to planning: the agent's map and flows first, then the data model
        # and the task graph built from the spec.
        diagrams=ir.diagrams + spec_diagrams(ir),
        change_areas=list(areas(ir.changes)) if ir.changes else [],
        change_summary=summarize(ir.changes) if ir.changes else "",
    )


def write_html(ir: SpecIR, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(ir, find_podcast(out.parent, ir.documents)), encoding="utf-8")
    return out
