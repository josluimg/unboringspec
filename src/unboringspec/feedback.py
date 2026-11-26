"""The reader's review, brought back into the project, and what became of it (#28).

A review is the Markdown the page exports (or copies for the agent). Besides the human text
it carries a hidden, machine-readable block:

    <!-- unboring:review {"version": "<documents hash>", "items": [...]} -->

Reviews live in .unboring/<feature>/reviews/. On the next render the latest one is mapped
onto the current version: which answers and notes were addressed, which approvals still hold,
and which marks can be carried over so the reader only reviews what is new or changed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .diff import _match, _norm, line_map
from .history import History
from .i18n import STRINGS
from .ir import FollowUp, FollowUpItem, SpecIR

BLOCK_RE = re.compile(r"<!--\s*unboring:review\s*(\{.*?\})\s*-->", re.DOTALL)


class ReviewItem(BaseModel):
    id: str = ""
    key: str
    kind: Literal["answer", "question", "approve"]
    text: str  # the question, or the decision's title
    choice: str = ""  # the decision's content, as reviewed
    cite: str = ""  # file:line in the reviewed version
    answer: str = ""
    note: str = ""


class SavedReview(BaseModel):
    version: str
    feature: str = ""
    created: str = ""
    items: list[ReviewItem] = Field(default_factory=list)


class ReviewError(ValueError):
    pass


def parse_review(text: str) -> SavedReview:
    m = BLOCK_RE.search(text)
    if not m:
        raise ReviewError(
            "No unboring:review block found. Export the review again from the page (Export review.md or "
            "Copy for your agent): older exports do not carry it."
        )
    try:
        return SavedReview.model_validate(json.loads(m.group(1)))
    except (json.JSONDecodeError, ValidationError) as e:
        raise ReviewError(f"The unboring:review block is not valid: {e}") from e


def reviews_dir(workdir: Path) -> Path:
    return workdir / "reviews"


def save_review(workdir: Path, text: str) -> tuple[Path, SavedReview]:
    review = parse_review(text)
    folder = reviews_dir(workdir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now():%Y%m%dT%H%M%S%f}.md"
    path.write_text(text, encoding="utf-8")
    return path, review


def latest_review(workdir: Path) -> tuple[Path, SavedReview] | None:
    folder = reviews_dir(workdir)
    for path in sorted(folder.glob("*.md"), reverse=True) if folder.is_dir() else []:
        try:
            return path, parse_review(path.read_text(encoding="utf-8"))
        except ReviewError:
            continue
    return None


def _when(path: Path) -> str:
    try:
        return datetime.strptime(path.stem, "%Y%m%dT%H%M%S%f").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return path.stem


def follow_up(review: SavedReview, reviewed_at: str, current: SpecIR, history: History) -> FollowUp:
    """Map each point of the review onto the current version."""
    from .history import documents_hash
    from .render import review_keys

    now_keys = review_keys(current)
    by_key = {k: i for i, k in now_keys.items()}
    decisions = {d.id: d for d in current.decisions}
    questions = {q.id: q for q in current.questions}
    same = review.version == documents_hash(current.documents)
    out = FollowUp(reviewed=f"your review of {reviewed_at}", reviewed_at=reviewed_at, same_version=same)

    # The reviewed version, to tell "changed" from "removed" and to follow reworded items.
    snapshot = history.find(review.version)
    baseline = History.load(snapshot) if snapshot else None
    if baseline is None and not same:
        out.notes.append(
            STRINGS["en"]["note_no_snapshot"]
        )
    lines = line_map(baseline.documents, current.documents) if baseline else None

    def counterpart(item: ReviewItem):
        """The current item a reviewed one became, or None if it is gone."""
        if item.key in by_key:
            return by_key[item.key], True  # identical
        pool = list(decisions.values()) if item.kind != "answer" else list(questions.values())
        if baseline is not None:
            old_keys = review_keys(baseline)
            old_id = next((i for i, k in old_keys.items() if k == item.key), None)
            olds = baseline.decisions if item.kind != "answer" else baseline.questions
            old = next((o for o in olds if o.id == old_id), None)
            if old is not None:
                if item.kind == "answer":
                    pairs, _, _ = _match([old], pool, key=lambda q: _norm(q.question), text=lambda q: q.question)
                else:
                    pairs, _, _ = _match([old], pool, key=lambda d: _norm(d.title),
                                         text=lambda d: f"{d.title} {d.choice}", lines=lines)
                if pairs:
                    return pairs[0][1].id, False
                return None, False
        # No snapshot: fall back to the title.
        for cur in pool:
            title = cur.question if item.kind == "answer" else cur.title
            if _norm(title) == _norm(item.text):
                return cur.id, False
        return None, False

    for item in review.items:
        current_id, identical = counterpart(item)
        key = now_keys.get(current_id, "") if current_id else ""
        src = []
        if current_id in decisions:
            src = decisions[current_id].sources[:1]
        elif current_id in questions:
            src = questions[current_id].sources[:1]

        if item.kind == "answer":
            if current_id is None:
                outcome = "addressed"  # the question is resolved
            else:
                outcome = "pending"
                out.carried[key] = {"answer": item.answer}
                out.flags[key] = STRINGS["en"]["flag_pending"]
                out.flag_codes[key] = {"code": "pending"}
            said = item.answer
        elif item.kind == "question":
            if current_id is None:
                outcome = "removed"
            elif identical:
                outcome = "not-addressed"
                out.carried[key] = {"v": "question", "note": item.note}
                out.flags[key] = STRINGS["en"]["flag_not-addressed"]
                out.flag_codes[key] = {"code": "not-addressed"}
            else:
                outcome = "changed"
                out.flags[key] = STRINGS["en"]["flag_changed"].format(note=item.note or "(none)")
                out.flag_codes[key] = {"code": "changed", "note": item.note}
            said = item.note
        else:  # approve
            if current_id is None:
                outcome = "removed"
            elif identical:
                outcome = "approved"
                out.carried[key] = {"v": "approve"}
            else:
                outcome = "approved-changed"
                out.flags[key] = STRINGS["en"]["flag_approved-changed"]
                out.flag_codes[key] = {"code": "approved-changed"}
            said = ""
        if same:
            # A review of this very version: everything simply carries over.
            if current_id and key:
                mark = {"answer": item.answer} if item.kind == "answer" else {"v": item.kind}
                if item.kind == "question":
                    mark["note"] = item.note
                out.carried[key] = mark
                out.flags.pop(key, None)
                out.flag_codes.pop(key, None)
            continue
        out.items.append(
            FollowUpItem(kind=item.kind, outcome=outcome, label=item.text, reader_said=said, key=key, sources=src)
        )

    order = ["approved-changed", "changed", "not-addressed", "pending", "addressed", "removed", "approved"]
    out.items.sort(key=lambda i: order.index(i.outcome))
    return out
