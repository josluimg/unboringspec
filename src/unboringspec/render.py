"""Render a SpecIR into a single self-contained HTML review page."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader

from . import __version__
from .diagrams import spec_diagrams
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


def render_html(ir: SpecIR, podcast: dict | None = None) -> str:
    env = Environment(loader=PackageLoader("unboringspec", "templates"), autoescape=True)
    tpl = env.get_template("review.html.j2")

    stories = {s.id: s for s in ir.stories}
    tasks_by_story: dict[str, list] = {}
    for t in ir.tasks:
        tasks_by_story.setdefault(t.story or "Shared", []).append(t)

    # Embedded as JSON for the source drawer and the review export. Escape "</" so a spec
    # containing "</script>" cannot break out of the script tag.
    payload = json.dumps(
        {
            "feature": ir.feature,
            "documents": ir.documents,
            "decisions": [{"id": d.id, "title": d.title, "choice": d.choice} for d in ir.decisions],
            "questions": [{"id": q.id, "question": q.question} for q in ir.questions],
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
        podcast=podcast,
        # From understanding to planning: the agent's map and flows first, then the data model
        # and the task graph built from the spec.
        diagrams=ir.diagrams + spec_diagrams(ir),
    )


def write_html(ir: SpecIR, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(ir, find_podcast(out.parent, ir.documents)), encoding="utf-8")
    return out
