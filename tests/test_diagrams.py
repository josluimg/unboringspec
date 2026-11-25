import json
from pathlib import Path

import pytest

from unboringspec.adapters import get_adapter
from unboringspec.adapters.base import data_model_entities, key_entities, merge_entities
from unboringspec.diagrams import MAX_TASK_NODES, check_mermaid, data_model, spec_diagrams, task_graph
from unboringspec.insights import apply_insights, heuristic_insights, parse_insights
from unboringspec.ir import Entity, SpecIR, Task
from unboringspec.render import render_html

ROOT = Path(__file__).parent.parent
SPECKIT = ROOT / "examples/speckit/specs/001-photo-albums"
OPENSPEC = ROOT / "examples/openspec/openspec/changes/add-invite-link-revocation"
EXAMPLE_INSIGHTS = ROOT / "schemas/examples/001-photo-albums.insights.json"


def load(path):
    return get_adapter(path).load(path)


# --- entities --------------------------------------------------------------------


def test_key_entities_from_speckit_spec():
    ir = load(SPECKIT)
    assert [(e.name, e.attributes) for e in ir.entities] == [
        ("Album", ["name", "owner", "invite token", "created at"]),
        ("Photo", ["file", "album", "uploader", "taken at", "uploaded at"]),
        ("Membership", ["user", "album", "role", "joined at"]),
    ]
    assert ir.entities[0].sources[0].label == "spec.md:63"


def test_data_model_md_formats():
    text = """# Data Model

## Album

| Name | Type |
|---|---|
| name | string |
| owner_id | uuid |

### Photo
- `file`: blob
- **album**: reference to Album
- **Validation**: under 25 MB
- taken_at — timestamp

## Membership
- **Fields**: user, album, role

## Relationships
- Album has many Photos
"""
    got = [(e.name, e.attributes) for e in data_model_entities(text, "data-model.md")]
    assert got == [
        ("Album", ["name", "owner_id"]),  # 'name' is data, not mistaken for the header
        ("Photo", ["file", "album", "taken_at"]),
        ("Membership", ["user", "album", "role"]),
    ]


def test_merge_entities_adds_missing_attributes():
    a = key_entities("### Key Entities\n- **Album**: name, owner.\n", "spec.md")
    b = data_model_entities("## Album\n- `name`: string\n- `cover`: photo\n", "data-model.md")
    merged = merge_entities(a, b)
    assert merged[0].attributes == ["name", "owner", "cover"]
    assert [s.file for s in merged[0].sources] == ["spec.md", "data-model.md"]


# --- spec diagrams ---------------------------------------------------------------


def test_data_model_infers_relationships():
    mermaid = data_model(load(SPECKIT)).mermaid
    assert mermaid.startswith("erDiagram")
    assert 'Album ||--o{ Photo : "has"' in mermaid
    assert 'Album ||--o{ Membership : "has"' in mermaid
    assert "field invite_token" in mermaid
    assert "User" not in mermaid  # 'user' names no known entity


def test_data_model_handles_ids_and_entities_without_attributes():
    ir = SpecIR(feature="x", framework="t", entities=[Entity(name="Order", attributes=["customer_id"]), Entity(name="Customer")])
    mermaid = data_model(ir).mermaid
    assert 'Customer ||--o{ Order : "has"' in mermaid
    assert "Customer {\n    field _\n  }" in mermaid


def test_task_graph_phases_parallel_and_done():
    d = task_graph(load(SPECKIT))
    m = d.mermaid
    assert d.title == "Task graph · 18 tasks in 6 phases"
    assert 'subgraph g0["1 · Setup"]' in m and 'subgraph g2["3 · US1"]' in m
    # T001 runs first, then T002 and T003 in parallel.
    assert "t_T001 --> t_T002" in m and "t_T001 --> t_T003" in m
    assert "class t_T001 ub_done" in m and "class t_T003 ub_parallel" in m
    # Phases are linked to each other, in order.
    assert "g0 --> g1" in m and "g4 --> g5" in m
    # No class names that collide with the page's own CSS.
    assert " done\n" not in m and " par\n" not in m


def test_task_graph_collapses_big_plans():
    tasks = [Task(id=f"T{i:03}", text="x", phase=f"Phase {i // 10}") for i in range(MAX_TASK_NODES + 5)]
    m = task_graph(SpecIR(feature="x", framework="t", tasks=tasks)).mermaid
    assert "subgraph" not in m and "10 tasks" in m


def test_openspec_task_groups():
    m = task_graph(load(OPENSPEC)).mermaid
    assert 'subgraph g0["Data model"]' in m and 'subgraph g3["Notifications"]' in m
    assert 't_1_1["1.1 Add `expires_at`' in m


def test_offline_page_opens_the_first_spec_diagram():
    html = render_html(heuristic_insights(load(SPECKIT)))
    assert '<details class="diagram" data-kind="data-model" open>' in html
    assert '<details class="diagram" data-kind="tasks">' in html


def test_prompt_asks_for_a_system_map_first():
    from unboringspec.insights import build_prompt

    prompt = build_prompt(load(SPECKIT))
    assert "1. system: the map of what is involved" in prompt
    assert prompt.index("1. system") < prompt.index("2. the main flow") < prompt.index("3. state")
    assert "only\n  those that apply" in prompt


def test_no_diagrams_without_tasks_or_entities():
    assert spec_diagrams(SpecIR(feature="x", framework="t")) == []


# --- agent diagrams ----------------------------------------------------------------


@pytest.mark.parametrize(
    "src,ok",
    [
        ("flowchart LR\n  A --> B", True),
        ("%% a comment\nsequenceDiagram\n  A->>B: hi", True),
        ("stateDiagram-v2\n  [*] --> Draft", True),
        ("", False),
        ("pie title Pets\n  \"Dogs\" : 3", False),  # not a supported type
        ("%%{init: {'securityLevel': 'loose'}}%%\nflowchart LR\n A --> B", False),
        ("flowchart LR\n  A --> B\n  click A callback", False),
        ("flowchart LR\n  A[<script>alert(1)</script>]", False),
        ("flowchart LR\n" + "  A --> B\n" * 600, False),
    ],
)
def test_check_mermaid(src, ok):
    assert (check_mermaid(src) is None) == ok


def test_agent_diagrams_are_kept_validated_and_capped():
    data = json.loads(EXAMPLE_INSIGHTS.read_text())
    ir, dropped = apply_insights(load(SPECKIT), parse_insights(json.dumps(data)), "agent")
    assert dropped == 0
    assert [(d.kind, d.origin) for d in ir.diagrams] == [("system", "agent"), ("journey", "agent"), ("sequence", "agent")]

    good = {"kind": "flow", "title": "Ok", "mermaid": "flowchart LR\n A-->B", "sources": [{"file": "spec.md", "line": 10}]}
    data["diagrams"] = [
        {"kind": "flow", "title": "Bad", "mermaid": "flowchart LR\n click A x", "sources": [{"file": "spec.md", "line": 10}]},
        {"kind": "flow", "title": "Uncited", "mermaid": "flowchart LR\n A-->B", "sources": [{"file": "spec.md", "line": 999}]},
        good,
        {**good, "title": "Fourth"},
    ]
    ir, dropped = apply_insights(load(SPECKIT), parse_insights(json.dumps(data)), "agent")
    # Two refused, one kept; the fourth is beyond the limit of three.
    assert [d.title for d in ir.diagrams] == ["Ok"] and dropped == 2


# --- page ------------------------------------------------------------------------


def test_page_shows_visual_overview_collapsed():
    ir, _ = apply_insights(load(SPECKIT), parse_insights(EXAMPLE_INSIGHTS.read_text()), "agent")
    html = render_html(ir)
    assert "· Visual overview</h2>" in html
    assert html.count('<details class="diagram"') == 5
    # From understanding to planning: the agent's map first, and open; spec diagrams after, closed.
    kinds = [chunk.split('"')[0] for chunk in html.split('<details class="diagram" data-kind="')[1:]]
    assert kinds == ["system", "journey", "sequence", "data-model", "tasks"]
    assert '<details class="diagram" data-kind="system" open>' in html
    assert '<details class="diagram" data-kind="data-model">' in html
    assert "from the spec" in html and "by the agent" in html
    assert "t_T001 --&gt; t_T002" in html  # Mermaid source is escaped, read back with textContent
    assert 'securityLevel: "strict"' in html


def test_page_without_diagrams_has_no_section():
    ir = heuristic_insights(load(ROOT / "tests/fixtures/spec-kit/drift/003-old-format"))
    assert "Visual overview" not in render_html(ir)


def test_page_escapes_spec_and_agent_text():
    """Specs and agent output are untrusted: nothing they contain may become live HTML."""
    ir = load(SPECKIT)
    ir.requirements[0].text = '<img src=x onerror="alert(1)">'
    ir.feature = "<script>alert(2)</script>"
    html = render_html(heuristic_insights(ir))
    assert '<img src=x onerror="alert(1)">' not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;img src=x onerror=" in html
