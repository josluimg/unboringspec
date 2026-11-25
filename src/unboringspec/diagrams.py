"""Mermaid diagrams for the review page.

Two origins:
- spec: built deterministically from what adapters extract (no LLM): the task graph and
  the data model.
- agent: written by the agent in insights.json (user journey, key sequence...). They are
  checked by `check_mermaid` before rendering; the browser then parses them with Mermaid
  and falls back to showing the source if they do not parse.
"""

from __future__ import annotations

import re

from .ir import Diagram, Entity, SpecIR, Task

AGENT_KINDS = {"journey", "sequence", "flow", "state"}
ALLOWED_TYPES = {
    "flowchart", "graph", "sequenceDiagram", "journey", "stateDiagram", "stateDiagram-v2", "erDiagram", "classDiagram",
}
MAX_MERMAID = 5000
# Anything that could change Mermaid's configuration or run code is refused, even though the
# page also renders with securityLevel "strict".
FORBIDDEN = re.compile(r"%%\{|<\s*script|javascript:|\bclick\b|\bcall\s|href|<\s*iframe|\bon\w+\s*=", re.IGNORECASE)
MAX_TASK_NODES = 40


def check_mermaid(source: str) -> str | None:
    """Return why a Mermaid diagram from an agent is refused, or None when it can be rendered."""
    src = source.strip()
    if not src:
        return "empty diagram"
    if len(src) > MAX_MERMAID:
        return f"diagram longer than {MAX_MERMAID} characters"
    first = next((line.strip() for line in src.splitlines() if line.strip() and not line.strip().startswith("%%")), "")
    kind = first.split()[0] if first else ""
    if kind not in ALLOWED_TYPES:
        return f"unsupported diagram type '{kind}'"
    if m := FORBIDDEN.search(src):
        return f"forbidden construct '{m.group(0).strip()}'"
    return None


# --- task graph --------------------------------------------------------------------


def _label(text: str, limit: int = 46) -> str:
    text = " ".join(text.split())
    text = text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
    return text.replace('"', "#quot;")


def _phase_label(name: str) -> str:
    """'Phase 3: User Story 1 - Create an album (P1)' -> '3 · US1'; 'Phase 1: Setup' -> '1 · Setup'.
    Mermaid wraps subgraph titles at a fixed width and the second line gets hidden, so titles stay
    short; the stories' full titles are on the page under Scope and plan."""
    name = re.sub(r"\s*\(P\d+\)\s*$", "", name)
    name = re.sub(r"^Phase\s+(\d+)\s*[:.-]\s*", r"\1 · ", name, flags=re.IGNORECASE)
    story = re.match(r"^(\d+ · )?User Story\s+(\d+)\b", name, flags=re.IGNORECASE)
    if story:
        return f"{story.group(1) or ''}US{story.group(2)}"
    return _label(name, 24)


def _node_id(task_id: str) -> str:
    return "t_" + re.sub(r"\W", "_", task_id)


def _groups(tasks: list[Task]) -> list[tuple[str, list[Task]]]:
    """Consecutive runs of tasks under the same phase (or story) heading."""
    groups: list[tuple[str, list[Task]]] = []
    for t in tasks:
        key = t.phase or t.story or "Tasks"
        if groups and groups[-1][0] == key:
            groups[-1][1].append(t)
        else:
            groups.append((key, [t]))
    return groups


def task_graph(ir: SpecIR) -> Diagram | None:
    """Phases run in order; inside a phase tasks run in order, except [P] tasks, which fan out
    in parallel. Big plans collapse to one node per phase so the graph stays readable."""
    if not ir.tasks:
        return None
    groups = _groups(ir.tasks)
    lines = ["flowchart TB"]
    if len(ir.tasks) > MAX_TASK_NODES:
        prev = None
        for n, (name, tasks) in enumerate(groups):
            done = sum(t.done for t in tasks)
            par = sum(t.parallel for t in tasks)
            extra = ", ".join(x for x in (f"{done} done" if done else "", f"{par} parallel" if par else "") if x)
            lines.append(f'  g{n}["{_phase_label(name)}<br/>{len(tasks)} tasks{" · " + extra if extra else ""}"]')
            if prev is not None:
                lines.append(f"  g{prev} --> g{n}")
            prev = n
    else:
        for n, (name, tasks) in enumerate(groups):
            lines.append(f'  subgraph g{n}["{_phase_label(name)}"]')
            lines.append("    direction LR")
            frontier: list[str] = []
            batch: list[str] = []
            for t in tasks:
                node = _node_id(t.id)
                lines.append(f'    {node}["{_label(t.id + " " + t.text)}"]')
                if t.done:
                    lines.append(f"    class {node} ub_done")
                if t.parallel:
                    lines.append(f"    class {node} ub_parallel")
                    batch.append(node)
                    continue
                if batch:
                    lines += [f"    {a} --> {b}" for a in frontier for b in batch]
                    frontier, batch = batch, []
                lines += [f"    {a} --> {node}" for a in frontier]
                frontier = [node]
            if batch:
                lines += [f"    {a} --> {b}" for a in frontier for b in batch]
            lines.append("  end")
        # Link phases to each other, not their nodes, so each phase keeps its left-to-right layout.
        lines += [f"  g{n} --> g{n + 1}" for n in range(len(groups) - 1)]
    # Prefixed class names: the page has its own .done and .par styles, which would leak into the SVG.
    lines.append("  classDef ub_done opacity:0.55")
    lines.append("  classDef ub_parallel stroke-dasharray:4 3")
    return Diagram(
        id="tasks",
        kind="tasks",
        title=f"Task graph · {len(ir.tasks)} tasks in {len(groups)} phases",
        mermaid="\n".join(lines),
        sources=ir.tasks[0].sources[:1],
    )


# --- data model --------------------------------------------------------------------


def _ident(name: str) -> str:
    return re.sub(r"\W+", "_", name.strip()).strip("_") or "x"


def _refers_to(attribute: str, entity: Entity) -> bool:
    a = re.sub(r"[\s_-]*(id|ref|reference)$", "", attribute.strip().lower())
    e = entity.name.strip().lower()
    return a in {e, e + "s"} or a.replace(" ", "_") == e.replace(" ", "_")


def data_model(ir: SpecIR) -> Diagram | None:
    """An entity-relationship diagram. A relationship is drawn when an attribute names another
    entity (Photo.album -> Album has many Photos); attributes have no types in most specs, so
    they are listed by name only."""
    if not ir.entities:
        return None
    lines = ["erDiagram"]
    for e in ir.entities:
        for other in ir.entities:
            if other is not e and any(_refers_to(a, other) for a in e.attributes):
                lines.append(f'  {_ident(other.name)} ||--o{{ {_ident(e.name)} : "has"')
    for e in ir.entities:
        attrs = list(dict.fromkeys(_ident(a).lower() for a in e.attributes))
        if attrs:
            lines.append(f"  {_ident(e.name)} {{")
            lines += [f"    field {a}" for a in attrs]
            lines.append("  }")
        else:
            lines.append(f"  {_ident(e.name)} {{\n    field _\n  }}")
    return Diagram(
        id="data-model",
        kind="data-model",
        title=f"Data model · {len(ir.entities)} entities",
        mermaid="\n".join(lines),
        sources=[s for e in ir.entities for s in e.sources[:1]],
    )


def spec_diagrams(ir: SpecIR) -> list[Diagram]:
    return [d for d in (data_model(ir), task_graph(ir)) if d]
