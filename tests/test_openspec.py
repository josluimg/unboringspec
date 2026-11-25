from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.adapters.openspec import OpenSpecAdapter
from unboringspec.cli import app
from unboringspec.insights import heuristic_insights
from unboringspec.ir import Attention
from unboringspec.render import render_html

ROOT = Path(__file__).parent.parent
V = Path(__file__).parent / "fixtures/openspec/v2.2.0/openspec"
CHANGE = V / "changes/add-invite-link-revocation"
ARCHIVED = V / "changes/archive/2026-10-01-digest-opt-out"
CAPABILITY = V / "specs/albums"
DRIFT = Path(__file__).parent / "fixtures/openspec/drift/openspec/changes/old-format"
EXAMPLE = ROOT / "examples/openspec/openspec/changes/add-invite-link-revocation"


def load(path):
    adapter = get_adapter(path)
    assert adapter.name == "openspec"
    return adapter.load(path)


# --- detection -------------------------------------------------------------------


@pytest.mark.parametrize("path", [CHANGE, ARCHIVED, CAPABILITY, DRIFT, EXAMPLE])
def test_detects_openspec_folders(path):
    assert get_adapter(path).name == "openspec"


def test_speckit_folders_are_not_taken():
    assert get_adapter(ROOT / "examples/speckit/specs/001-photo-albums").name == "spec-kit"
    assert not OpenSpecAdapter.detect(ROOT / "tests/fixtures/spec-kit/v1.4.4/002-login")


# --- a change in the v2.2.0 template style -----------------------------------------


def test_change_title_why_and_document_order():
    ir = load(CHANGE)
    assert ir.feature == "Add invite link revocation"
    assert ir.description.startswith("Album invite links never expire")
    assert list(ir.documents) == [
        "proposal.md", "design.md", "specs/albums/spec.md", "specs/notifications/spec.md", "tasks.md"
    ]
    assert ir.warnings == []


def test_every_delta_operation_is_tagged_and_cited():
    ir = load(CHANGE)
    ops = [(r.change, r.text.split(" (")[0]) for r in ir.requirements]
    assert ops == [
        ("added", "Revoke invite link"),
        ("added", "Owner deletes any photo"),
        ("modified", "Join album via invite link"),
        ("removed", "Permanent invite link"),
        ("renamed", "Album invite → Album invite link"),
        ("added", "Warn before a link expires"),
    ]
    revoke = ir.requirements[0]
    assert "(albums): The album owner SHALL be able to revoke" in revoke.text
    removed = ir.requirements[3]
    assert "Reason: Permanent links cannot be revoked" in removed.text and "Migration:" in removed.text
    for r in ir.requirements:
        line = ir.documents[r.sources[0].file].splitlines()[r.sources[0].line - 1]
        assert "Requirement:" in line


def test_breaking_change_needs_a_human():
    ir = load(CHANGE)
    breaking = [d for d in ir.decisions if d.title == "Breaking change"]
    assert len(breaking) == 1 and breaking[0].attention == Attention.decide
    assert breaking[0].choice.startswith("Permanent invite links are removed")


def test_design_decisions_risks_and_open_questions():
    ir = load(CHANGE)
    titles = [d.title for d in ir.decisions if d.id.startswith("D")]
    assert titles == [
        "Rotate the token instead of keeping a denylist",
        "Store an expiry next to the token",
        "Owners moderate photos, members do not",
    ]
    assert ir.risks[0].title == "Relatives with an old link are locked out after rotation"
    assert ir.risks[0].mitigation.startswith("The join page explains")
    assert [q.question for q in ir.questions] == [
        "What should the default link lifetime be: 7, 30 or 90 days?",
        "Should members who joined through a revoked link stay in the album?",
    ]
    assert [q.id for q in ir.questions] == ["Q1", "Q2"]


def test_tasks_keep_numbers_groups_and_state():
    ir = load(CHANGE)
    assert [(t.id, t.story, t.done) for t in ir.tasks[:3]] == [
        ("1.1", "Data model", True), ("1.2", "Data model", False), ("2.1", "API", False)
    ]
    assert len(ir.tasks) == 8


# --- real-world drift from the templates -------------------------------------------


def test_freeform_archived_change():
    ir = load(ARCHIVED)
    assert ir.feature == "Digest opt out"  # date prefix dropped, no '# Proposal' heading
    assert [d.title for d in ir.decisions] == ["Unsubscribe link", "Preference storage"]
    assert [t.id for t in ir.tasks] == ["T1", "T2", "T3"] and all(t.done for t in ir.tasks)
    assert ir.requirements[0].change == "added"
    assert ir.warnings == []


def test_capability_spec():
    ir = load(CAPABILITY)
    assert ir.feature == "Albums"
    assert ir.description.startswith("Families create shared albums")
    assert [(r.change, r.text.split(":")[0]) for r in ir.requirements] == [("", "Create album"), ("", "Album invite link")]


def test_format_drift_is_reported():
    ir = load(DRIFT)
    assert len(ir.warnings) == 3
    assert all("OpenSpec v2.2.0" in w for w in ir.warnings)


def test_missing_deltas_respect_skip_specs(tmp_path):
    change = tmp_path / "openspec/changes/refactor-only"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("## Why\n\nTidy up.\n\n## What Changes\n\n- Refactor.\n")
    (change / "tasks.md").write_text("- [ ] 1.1 Refactor\n")
    assert any("no spec deltas" in w for w in load(change).warnings)
    (change / ".openspec.yaml").write_text("schema: spec-driven\nskip_specs: true\n")
    assert load(change).warnings == []


# --- end to end ------------------------------------------------------------------


def test_offline_review_shows_delta_tags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["review", str(EXAMPLE), "--offline"])
    assert r.exit_code == 0, r.output
    html = (tmp_path / ".unboring/add-invite-link-revocation/review.html").read_text()
    for op in ("added", "modified", "removed", "renamed"):
        assert f"tag-change-{op}" in html
    assert "Breaking change" in html


def test_summary_counts_requirement_changes():
    ir = heuristic_insights(load(CHANGE))
    assert "6 requirement changes (3 added, 1 modified, 1 removed, 1 renamed)" in ir.summary.bullets
    assert any("Breaking change" in item for item in ir.summary.you_must_decide)
    render_html(ir)  # renders without error


def test_example_matches_fixture():
    for f in CHANGE.rglob("*"):
        if f.is_file():
            assert (EXAMPLE / f.relative_to(CHANGE)).read_text() == f.read_text(), f"{f.name} differs"
