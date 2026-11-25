"""Applying a review through the framework's own commands (#32)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.apply import invocation_for, plan_apply
from unboringspec.cli import app
from unboringspec.feedback import ReviewItem, SavedReview
from unboringspec.history import documents_hash
from unboringspec.insights import heuristic_insights
from unboringspec.integrations import skill_body
from unboringspec.render import render_html, review_keys

ROOT = Path(__file__).parent.parent
SPECKIT = ROOT / "tests/fixtures/spec-kit/iterations/v1/001-photo-albums"
OPENSPEC = ROOT / "examples/openspec/openspec/changes/add-invite-link-revocation"
runner = CliRunner()


def load(path):
    ad = get_adapter(path)
    ir = heuristic_insights(ad.load(path))
    ir.folder = path.name
    return ad, ir


def review(ir, marks):
    keys = review_keys(ir)
    items = []
    for kind, text, extra in marks:
        if kind == "answer":
            q = next(q for q in ir.questions if q.question == text)
            items.append(ReviewItem(id=q.id, key=keys[q.id], kind=kind, text=text, cite=q.sources[0].label, answer=extra))
        else:
            d = next(d for d in ir.decisions if d.title == text)
            items.append(ReviewItem(id=d.id, key=keys[d.id], kind=kind, text=text, choice=d.choice, cite=d.sources[0].label, note=extra))
    return SavedReview(version=documents_hash(ir.documents), items=items)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: h))
    return h


# --- spec-kit --------------------------------------------------------------------


def test_speckit_routes_points_to_the_command_that_owns_their_file(tmp_path, home):
    ad, ir = load(SPECKIT)
    r = review(ir, [
        ("answer", "should links expire or be revocable?", "Revocable, 90 days"),   # spec.md
        ("answer", "monthly storage budget per family", "10 GB"),                    # plan.md
        ("question", "Digest delivery", "half-hour timezones?"),                    # research.md
        ("approve", "Upload path", ""),
    ])
    steps = plan_apply(r, ir, ad, SPECKIT, tmp_path)
    assert [(p.step.id, len(p.items)) for p in steps] == [("clarify", 1), ("plan", 2), ("tasks", 0), ("analyze", 0)]
    clarify = steps[0].input_file.read_text()
    assert "- Q: should links expire or be revocable? (spec.md:45) → A: Revocable, 90 days" in clarify
    assert "do not ask them again" in clarify
    assert "Upload path" not in clarify  # approvals need no command
    plan = steps[1].input_file.read_text()
    assert "monthly storage budget" in plan and "Reviewer: half-hour timezones?" in plan
    assert steps[2].input_file is None and steps[3].step.optional


def test_only_the_steps_that_have_work(tmp_path, home):
    ad, ir = load(SPECKIT)
    only_spec = review(ir, [("answer", "should links expire or be revocable?", "Revocable")])
    assert [p.step.id for p in plan_apply(only_spec, ir, ad, SPECKIT, tmp_path)] == ["clarify", "tasks", "analyze"]
    only_approvals = review(ir, [("approve", "Upload path", "")])
    assert plan_apply(only_approvals, ir, ad, SPECKIT, tmp_path) == []


@pytest.mark.parametrize(
    "installed,expected",
    [
        (".claude/skills/speckit-clarify/SKILL.md", "/speckit-clarify"),
        (".claude/commands/speckit.clarify.md", "/speckit.clarify"),
        (".github/prompts/speckit.clarify.prompt.md", "/speckit.clarify"),
        (".agents/skills/speckit-clarify/SKILL.md", "/speckit-clarify"),
        (".gemini/commands/speckit.clarify.toml", "/speckit.clarify"),
    ],
)
def test_speckit_invocation_follows_how_it_was_installed(tmp_path, home, installed, expected):
    project = tmp_path / "project"
    spec = project / "specs/001-photo-albums"
    shutil.copytree(SPECKIT, spec)
    (project / ".specify").mkdir()
    (project / installed).parent.mkdir(parents=True, exist_ok=True)
    (project / installed).write_text("x")
    ad, ir = load(spec)
    r = review(ir, [("answer", "should links expire or be revocable?", "Revocable")])
    clarify = plan_apply(r, ir, ad, spec, tmp_path / "wd")[0]
    assert clarify.invocation == expected and clarify.installed


def test_commands_installed_in_the_home_folder_are_found(tmp_path, home):
    (home / ".claude/skills/speckit-clarify").mkdir(parents=True)
    (home / ".claude/skills/speckit-clarify/SKILL.md").write_text("x")
    ad, ir = load(SPECKIT)
    r = review(ir, [("answer", "should links expire or be revocable?", "Revocable")])
    assert plan_apply(r, ir, ad, SPECKIT, tmp_path)[0].invocation == "/speckit-clarify"


# --- OpenSpec and generic ----------------------------------------------------------


def test_openspec_folds_everything_into_update(tmp_path, home):
    ad, ir = load(OPENSPEC)
    d = ir.decisions[1]
    keys = review_keys(ir)
    r = SavedReview(version="x", items=[
        ReviewItem(key=keys[d.id], kind="question", text=d.title, choice=d.choice, cite=d.sources[0].label, note="why rotate?"),
        ReviewItem(key=keys[ir.decisions[2].id], kind="approve", text=ir.decisions[2].title, cite=ir.decisions[2].sources[0].label),
    ])
    steps = plan_apply(r, ir, ad, OPENSPEC, tmp_path)
    assert [(p.step.id, p.invocation) for p in steps] == [("update", "/opsx:update add-invite-link-revocation")]
    text = steps[0].input_file.read_text()
    assert "Reviewer: why rotate?" in text and "Approved by the reviewer (leave as is)" in text


def test_openspec_invocation_keeps_the_change_id():
    assert invocation_for(".claude/commands/opsx/update.md", "/opsx:update add-2fa") == "/opsx:update add-2fa"
    assert invocation_for("/home/x/.claude/skills/openspec-update-change/SKILL.md", "/opsx:update add-2fa") == "/openspec-update-change add-2fa"


def test_generic_specs_are_edited_directly(tmp_path, home):
    folder = tmp_path / "rfc"
    folder.mkdir()
    (folder / "rfc.md").write_text("# Search\n\n- [NEEDS CLARIFICATION: which index?]\n")
    ad, ir = load(folder)
    keys = review_keys(ir)
    q = ir.questions[0]
    r = SavedReview(version="x", items=[ReviewItem(key=keys[q.id], kind="answer", text=q.question, cite=q.sources[0].label, answer="Postgres FTS")])
    steps = plan_apply(r, ir, ad, folder, tmp_path / "wd")
    assert [(p.step.id, p.invocation) for p in steps] == [("edit", None)]


# --- CLI, skill, page --------------------------------------------------------------


def test_feedback_prints_the_steps(tmp_path, monkeypatch, home):
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "specs/001-photo-albums"
    shutil.copytree(SPECKIT, spec)
    ad, ir = load(spec)
    r = review(ir, [("answer", "should links expire or be revocable?", "Revocable"), ("question", "Digest delivery", "tz?")])
    md = "# Review\n<!-- unboring:review " + json.dumps(r.model_dump()) + " -->\n"
    out = runner.invoke(app, ["feedback", str(spec), "-"], input=md).output
    assert "Do not edit the spec files directly" in out
    assert "1. /speckit.clarify" in out and "2. /speckit.plan" in out and "3. /speckit.tasks" in out
    assert "Not found in this project or your home folder: /speckit.clarify, /speckit.plan, /speckit.tasks." in out
    assert "/speckit.analyze." not in out.split("Not found")[1]  # optional steps never warn
    again = runner.invoke(app, ["feedback", str(spec)]).output
    assert again.startswith("Shared Photo Albums") and "Using " in again


def test_skill_forbids_editing_when_the_framework_has_commands():
    body = skill_body("unboring-review")
    assert "Never edit spec files yourself when the framework" in body
    assert "If it warns that a command is not installed**, tell the user and stop" in body


def test_exported_review_names_the_framework_commands():
    _, ir = load(SPECKIT)
    html = render_html(ir)
    assert "Apply this review with spec-kit's own commands (/speckit.clarify, /speckit.plan, /speckit.tasks)" in html
    assert "if (data.apply_hint) out.push(`> ${data.apply_hint}`" in html


# --- spec-kit's active feature -------------------------------------------------------


def _speckit_project(tmp_path):
    project = tmp_path / "project"
    spec = project / "specs/001-photo-albums"
    shutil.copytree(SPECKIT, spec)
    (project / ".specify").mkdir()
    return project, spec


def test_no_active_feature_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    project, spec = _speckit_project(tmp_path)
    [msg] = get_adapter(spec).apply_checks(spec)
    assert "no active feature" in msg and '{"feature_directory": "specs/001-photo-albums"}' in msg


def test_another_active_feature_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    project, spec = _speckit_project(tmp_path)
    (project / ".specify/feature.json").write_text('{"feature_directory": "specs/002-login"}')
    [msg] = get_adapter(spec).apply_checks(spec)
    assert "active feature is specs/002-login, not specs/001-photo-albums" in msg and "Ask the user" in msg


def test_matching_active_feature_needs_nothing(tmp_path, monkeypatch):
    project, spec = _speckit_project(tmp_path)
    (project / ".specify/feature.json").write_text('{"feature_directory": "specs/001-photo-albums"}')
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    assert get_adapter(spec).apply_checks(spec) == []
    monkeypatch.setenv("SPECIFY_FEATURE_DIRECTORY", "specs/002-login")  # the env var wins, like in spec-kit
    assert "active feature is specs/002-login" in get_adapter(spec).apply_checks(spec)[0]


def test_specs_outside_a_speckit_project_are_not_checked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .specify anywhere up the tree
    spec = tmp_path / "specs/001-photo-albums"
    shutil.copytree(SPECKIT, spec)
    assert get_adapter(spec).apply_checks(spec) == []


def test_feedback_warns_before_the_steps(tmp_path, monkeypatch, home):
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    project, spec = _speckit_project(tmp_path)
    monkeypatch.chdir(project)
    ad, ir = load(spec)
    r = review(ir, [("answer", "should links expire or be revocable?", "Revocable")])
    md = "# Review\n<!-- unboring:review " + json.dumps(r.model_dump()) + " -->\n"
    out = runner.invoke(app, ["feedback", "specs/001-photo-albums", "-"], input=md).output
    assert out.index("Before you start") < out.index("1. /speckit.clarify")
