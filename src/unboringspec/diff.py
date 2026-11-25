"""Semantic diff between two versions of a spec's analysis (SpecIR).

The point is not a text diff: a reviewer on iteration N+1 wants to know which decisions,
questions, requirements and tasks changed. Items are matched by stable keys where the
framework gives them (FR-001, US1, T001) and by similarity where the text is written by an
agent (decisions, risks, questions), so rewording does not show up as removed + added.
"""

from __future__ import annotations

import difflib
import re
from typing import Callable, Iterable, TypeVar

from .ir import ChangeItem, ChangeSet, FileDelta, SpecIR

T = TypeVar("T")
FUZZY = 0.75  # two texts are the same item above this similarity
SAME_TEXT = 0.92  # and unchanged above this one
STABLE_REQ_ID = re.compile(r"^(FR|NFR|SC)-\d+$")
ORDER = ["question", "decision", "requirement", "story", "entity", "task", "risk"]


def _norm(text: str) -> str:
    """Lowercase words only, so punctuation and spacing never count as a change."""
    return " ".join(re.sub(r"[^\w ]+", " ", text.lower()).split())


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def line_map(before: dict[str, str], after: dict[str, str]) -> dict[tuple[str, int], int]:
    """Where each line of the previous version is now: (file, old line) -> new line.
    Unchanged lines follow insertions and deletions; edited lines keep their position in the block."""
    out: dict[tuple[str, int], int] = {}
    for name in set(before) & set(after):
        old, new = before[name].splitlines(), after[name].splitlines()
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag in ("equal", "replace"):
                for k in range(min(i2 - i1, j2 - j1)):
                    out[(name, i1 + k + 1)] = j1 + k + 1
    return out


def _match(
    before: list[T],
    after: list[T],
    key: Callable[[T], str],
    text: Callable[[T], str],
    lines: dict[tuple[str, int], int] | None = None,
) -> tuple[list[tuple[T, T]], list[T], list[T]]:
    """Pair items by key, then by text similarity, then (when `lines` is given) by citing the
    same line of the documents. Returns (pairs, removed, added)."""
    pairs: list[tuple[T, T]] = []
    left = list(before)
    right = list(after)
    by_key = {key(b): b for b in left}
    for a in list(right):
        b = by_key.get(key(a))
        if b is not None and b in left:
            pairs.append((b, a))
            left.remove(b)
            right.remove(a)
    for a in list(right):
        best = max(left, key=lambda b: _ratio(text(b), text(a)), default=None)
        if best is not None and _ratio(text(best), text(a)) >= FUZZY:
            pairs.append((best, a))
            left.remove(best)
            right.remove(a)
    if lines is not None:
        # An agent may retitle and rewrite a decision completely; if both versions cite the
        # same line of the spec, it is the same decision, changed.
        for a in list(right):
            cited = {(c.file, c.line) for c in a.sources}
            for b in left:
                moved = {(c.file, lines.get((c.file, c.line))) for c in b.sources}
                if cited & moved:
                    pairs.append((b, a))
                    left.remove(b)
                    right.remove(a)
                    break
    return pairs, left, right


def _changed(a: str, b: str, exact: bool = True) -> bool:
    """Text from the documents changes when any word does ('MUST' -> 'SHOULD' matters).
    Text written by an agent is reworded between runs, so it only changes when it differs a lot."""
    return _norm(a) != _norm(b) if exact else _ratio(a, b) < SAME_TEXT


def _was_at(item) -> str:
    return item.sources[0].label if getattr(item, "sources", None) else ""


def _family(generated_by: str) -> str:
    return "heuristic" if generated_by == "heuristic" else "llm"


def _is_marker(question, docs: dict[str, str]) -> bool:
    """A question that comes from a [NEEDS CLARIFICATION] marker in the documents."""
    if not question.sources:
        return False
    s = question.sources[0]
    lines = docs.get(s.file, "").splitlines()
    return 0 < s.line <= len(lines) and "NEEDS CLARIFICATION" in lines[s.line - 1].upper()


def file_deltas(before: dict[str, str], after: dict[str, str]) -> list[FileDelta]:
    out = []
    for name in sorted(set(before) | set(after)):
        if name not in before:
            out.append(FileDelta(file=name, added=len(after[name].splitlines()), status="added"))
        elif name not in after:
            out.append(FileDelta(file=name, removed=len(before[name].splitlines()), status="removed"))
        elif before[name] != after[name]:
            added = removed = 0
            for line in difflib.ndiff(before[name].splitlines(), after[name].splitlines()):
                added += line.startswith("+ ")
                removed += line.startswith("- ")
            out.append(FileDelta(file=name, added=added, removed=removed))
    return out


def compare(before: SpecIR, after: SpecIR, baseline: str) -> ChangeSet:
    items: list[ChangeItem] = []
    notes: list[str] = []
    lines = line_map(before.documents, after.documents)
    same_family = _family(before.generated_by) == _family(after.generated_by)

    def add(area, change, label, item=None, previous=None, before_text="", after_text=""):
        items.append(
            ChangeItem(
                area=area,
                change=change,
                label=label,
                before=before_text,
                after=after_text,
                sources=list(item.sources[:1]) if item is not None else [],
                was_at=_was_at(previous) if previous is not None and item is None else "",
            )
        )

    # Questions: a question that disappears was resolved; that is usually the good news.
    q_before, q_after = before.questions, after.questions
    if not same_family:
        q_before = [q for q in q_before if _is_marker(q, before.documents)]
        q_after = [q for q in q_after if _is_marker(q, after.documents)]
    _, gone, new = _match(q_before, q_after, key=lambda q: _norm(q.question), text=lambda q: q.question)
    for q in gone:
        add("question", "resolved", q.question, previous=q)
    for q in new:
        add("question", "added", q.question, item=q)

    # Decisions: when one version was analysed by an agent and the other offline, only the
    # decisions recorded in the documents themselves can be compared fairly.
    d_before, d_after = before.decisions, after.decisions
    if not same_family:
        d_before = [d for d in d_before if d.id.startswith(("TC", "B"))]
        d_after = [d for d in d_after if d.id.startswith(("TC", "B"))]
        notes.append(
            "The two versions were analysed differently (offline and by an agent), so only decisions "
            "written in the documents are compared."
        )
    pairs, gone, new = _match(
        d_before, d_after, key=lambda d: _norm(d.title), text=lambda d: f"{d.title} {d.choice}", lines=lines
    )
    for b, a in pairs:
        from_documents = _family(after.generated_by) == "heuristic" or a.id.startswith(("TC", "B"))
        if _changed(b.choice, a.choice, exact=from_documents):
            old = b.choice if _norm(b.title) == _norm(a.title) else f"{b.title}: {b.choice}"
            add("decision", "changed", a.title, item=a, before_text=old, after_text=a.choice)
        elif b.attention != a.attention:
            add("decision", "changed", a.title, item=a, before_text=f"attention: {b.attention.value}",
                after_text=f"attention: {a.attention.value}")
    for d in gone:
        add("decision", "removed", d.title, previous=d, before_text=d.choice)
    for d in new:
        add("decision", "added", d.title, item=d, after_text=d.choice)

    # Requirements: stable IDs in spec-kit, requirement names in OpenSpec.
    def req_key(r):
        return r.id if STABLE_REQ_ID.match(r.id) else _norm(r.text.split(":")[0])

    pairs, gone, new = _match(before.requirements, after.requirements, key=req_key, text=lambda r: r.text)
    for b, a in pairs:
        if _changed(b.text, a.text) or b.change != a.change:
            label = a.id if STABLE_REQ_ID.match(a.id) else a.text.split(":")[0]
            add("requirement", "changed", label, item=a, before_text=b.text, after_text=a.text)
    for r in gone:
        add("requirement", "removed", r.id if STABLE_REQ_ID.match(r.id) else r.text.split(":")[0],
            previous=r, before_text=r.text)
    for r in new:
        add("requirement", "added", r.id if STABLE_REQ_ID.match(r.id) else r.text.split(":")[0], item=r, after_text=r.text)

    # Stories.
    pairs, gone, new = _match(before.stories, after.stories, key=lambda s: s.id, text=lambda s: s.title)
    for b, a in pairs:
        old, cur = f"{b.priority} {b.title}".strip(), f"{a.priority} {a.title}".strip()
        if old != cur:
            add("story", "changed", f"{a.id} {a.title}", item=a, before_text=old, after_text=cur)
    for s in gone:
        add("story", "removed", f"{s.id} {s.title}", previous=s)
    for s in new:
        add("story", "added", f"{s.id} {s.title}", item=s)

    # Entities and their attributes.
    pairs, gone, new = _match(before.entities, after.entities, key=lambda e: e.name.lower(), text=lambda e: e.name)
    for b, a in pairs:
        plus = [x for x in a.attributes if x not in b.attributes]
        minus = [x for x in b.attributes if x not in a.attributes]
        if plus or minus:
            detail = ", ".join([f"+{x}" for x in plus] + [f"−{x}" for x in minus])
            add("entity", "changed", a.name, item=a, after_text=detail)
    for e in gone:
        add("entity", "removed", e.name, previous=e)
    for e in new:
        add("entity", "added", e.name, item=e, after_text=", ".join(e.attributes))

    # Tasks: new, removed, completed, reopened, reworded.
    pairs, gone, new = _match(before.tasks, after.tasks, key=lambda t: t.id, text=lambda t: t.text)
    for b, a in pairs:
        if not b.done and a.done:
            add("task", "completed", f"{a.id} {a.text}", item=a)
        elif b.done and not a.done:
            add("task", "reopened", f"{a.id} {a.text}", item=a)
        if _changed(b.text, a.text):
            add("task", "changed", a.id, item=a, before_text=b.text, after_text=a.text)
    for t in gone:
        add("task", "removed", f"{t.id} {t.text}", previous=t)
    for t in new:
        add("task", "added", f"{t.id} {t.text}", item=t)

    # Risks only make sense between two analyses of the same kind.
    if same_family:
        _, gone, new = _match(
            before.risks, after.risks, key=lambda r: _norm(r.title), text=lambda r: r.title, lines=lines
        )
        for r in gone:
            add("risk", "removed", r.title, previous=r)
        for r in new:
            add("risk", "added", r.title, item=r)

    items.sort(key=lambda i: ORDER.index(i.area))
    return ChangeSet(baseline=baseline, items=items, files=file_deltas(before.documents, after.documents), notes=notes)


def summarize(changes: ChangeSet) -> str:
    counts: dict[str, int] = {}
    for i in changes.items:
        counts[i.change] = counts.get(i.change, 0) + 1
    if not counts:
        return "no semantic changes"
    return ", ".join(f"{n} {c}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def areas(changes: ChangeSet) -> Iterable[tuple[str, list[ChangeItem]]]:
    for area in ORDER:
        group = [i for i in changes.items if i.area == area]
        if group:
            yield area, group
