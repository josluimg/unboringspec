from pathlib import Path

from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.insights import LLMInsights, _resolve, Citation
from unboringspec.ir import Attention
from unboringspec.render import render_html

EXAMPLE = Path(__file__).parent.parent / "examples/speckit/specs/001-photo-albums"


def load():
    ad = get_adapter(EXAMPLE)
    assert ad.name == "spec-kit"
    return ad.load(EXAMPLE)


def test_parses_structure():
    ir = load()
    assert ir.feature == "Shared Photo Albums"
    assert ir.description.startswith("Let families create shared photo albums")
    assert [s.id for s in ir.stories] == ["US1", "US2", "US3"]
    assert ir.stories[0].priority == "P1"
    assert len([r for r in ir.requirements if r.id.startswith("FR")]) == 7
    assert len(ir.tasks) == 18
    t9 = next(t for t in ir.tasks if t.id == "T009")
    assert t9.parallel and t9.story == "US1" and not t9.done
    assert next(t for t in ir.tasks if t.id == "T001").done


def test_finds_clarifications_with_sources():
    ir = load()
    assert len(ir.questions) == 4
    files = {q.sources[0].file for q in ir.questions}
    assert files == {"spec.md", "plan.md"}
    for q in ir.questions:
        line = ir.documents[q.sources[0].file].splitlines()[q.sources[0].line - 1]
        assert "NEEDS CLARIFICATION" in line


def test_decisions_and_attention():
    ir = load()
    research = [d for d in ir.decisions if d.id.startswith("D")]
    assert len(research) == 4
    invite = next(d for d in research if d.title == "Invite model")
    assert "permanent invite token" in invite.choice
    assert len(invite.alternatives) == 3
    # Unresolved tech-context fields are questions, not duplicated as decisions.
    assert not any(d.title == "Constraints" for d in ir.decisions)
    assert all(d.attention == Attention.routine for d in ir.decisions if d.id.startswith("TC"))
    assert ir.questions[0].sources[0].file == "spec.md"


def test_resolve_drops_invented_citations():
    docs = {"spec.md": "a\nb\nc"}
    refs = _resolve([Citation(file="spec.md", line=2), Citation(file="spec.md", line=99), Citation(file="nope.md", line=1)], docs)
    assert [(r.file, r.line, r.excerpt) for r in refs] == [("spec.md", 2, "b")]


def test_llm_schema_is_valid_json_schema():
    schema = LLMInsights.model_json_schema()
    assert "decisions" in schema["properties"]


def test_render_escapes_script_breakout():
    ir = load()
    ir.documents["evil.md"] = "</script><script>alert(1)</script>"
    html = render_html(ir)
    assert "</script><script>alert(1)" not in html


def test_cli_offline(tmp_path):
    out = tmp_path / "review.html"
    result = CliRunner().invoke(app, ["review", str(EXAMPLE), "--offline", "-o", str(out)])
    assert result.exit_code == 0, result.output
    html = out.read_text()
    assert "Shared Photo Albums" in html
    assert "Needs your judgment" in html
    assert "spec.md:" in html
