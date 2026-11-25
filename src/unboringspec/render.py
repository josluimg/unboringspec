"""Render a SpecIR into a single self-contained HTML review page."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from . import __version__
from .ir import Attention, SpecIR


def render_html(ir: SpecIR) -> str:
    env = Environment(loader=PackageLoader("unboringspec", "templates"), autoescape=select_autoescape(["html"]))
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
    )


def write_html(ir: SpecIR, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(ir), encoding="utf-8")
    return out
