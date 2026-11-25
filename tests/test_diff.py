import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.diff import compare, summarize
from unboringspec.history import KEEP, History
from unboringspec.insights import apply_insights, heuristic_insights, parse_insights
from unboringspec.render import render_html

ROOT = Path(__file__).parent.parent
V1 = Path(__file__).parent / "fixtures/spec-kit/iterations/v1/001-photo-albums"
V2 = Path(__file__).parent / "fixtures/spec-kit/iterations/v2/001-photo-albums"
runner = CliRunner()


def analysed(path):
    return heuristic_insights(get_adapter(path).load(path))


# --- semantic diff -----------------------------------------------------------------


def test_diff_between_two_iterations():
    changes = compare(analysed(V1), analysed(V2), "v1")
    got = {(i.area, i.change, i.label.split(" ")[0]) for i in changes.items}
    assert got == {
        ("question", "resolved", "should"),     # leaked link: answered
        ("question", "resolved", "retention"),  # retention period: answered
        ("decision", "changed", "Invite"),
        ("requirement", "changed", "FR-004"),
        ("requirement", "changed", "FR-007"),
        ("requirement", "added", "FR-008"),
        ("story", "changed", "US3"),
        ("entity", "changed", "Album"),
        ("task", "completed", "T003"),
        ("task", "removed", "T018"),
        ("task", "added", "T019"),
    }
    assert summarize(changes) == "5 changed, 2 resolved, 2 added, 1 completed, 1 removed"


def test_diff_details_point_to_the_right_lines():
    changes = compare(analysed(V1), analysed(V2), "v1")
    by = {(i.area, i.change, i.label.split(" ")[0]): i for i in changes.items}
    fr4 = by[("requirement", "changed", "FR-004")]
    assert "Anyone with an invite link" in fr4.before and "valid, unexpired" in fr4.after
    assert fr4.sources[0].label == "spec.md:56"
    removed = by[("task", "removed", "T018")]
    assert removed.sources == [] and removed.was_at == "tasks.md:37"  # no longer in the current files
    assert by[("story", "changed", "US3")].before.startswith("P2") and by[("story", "changed", "US3")].after.startswith("P3")
    assert by[("entity", "changed", "Album")].after == "+invite expires at"
    files = {f.file: (f.added, f.removed) for f in changes.files}
    assert files == {"research.md": (1, 1), "spec.md": (6, 5), "tasks.md": (2, 2)}


def test_no_changes_against_itself():
    changes = compare(analysed(V1), analysed(V1), "same")
    assert changes.items == [] and changes.files == [] and summarize(changes) == "no semantic changes"


def _agent(path):
    ir, _ = apply_insights(
        get_adapter(path).load(path), parse_insights((ROOT / "schemas/examples/001-photo-albums.insights.json").read_text()), "agent"
    )
    return ir


def test_rewording_by_an_agent_is_not_a_change():
    before, after = _agent(V1), _agent(V1)
    d = after.decisions[0]
    d.title = d.title + "."  # punctuation only
    d.choice = "The " + d.choice[0].lower() + d.choice[1:]  # light rewording
    assert [i for i in compare(before, after, "x").items if i.area == "decision"] == []


def test_one_word_in_the_documents_is_a_change():
    before, after = analysed(V1), analysed(V1)
    fr = next(r for r in after.requirements if r.id == "FR-006")
    fr.text = fr.text.replace("MUST", "SHOULD")
    assert [(i.label, i.change) for i in compare(before, after, "x").items] == [("FR-006", "changed")]


def test_offline_vs_agent_compares_only_what_the_documents_say():
    offline = analysed(V1)
    agent, _ = apply_insights(
        get_adapter(V1).load(V1), parse_insights((ROOT / "schemas/examples/001-photo-albums.insights.json").read_text()), "agent"
    )
    changes = compare(offline, agent, "offline run")
    assert any("analysed differently" in n for n in changes.notes)
    assert all(i.area != "risk" for i in changes.items)
    # Agent questions are not 'new' just because the offline run could not produce them.
    assert all(i.area != "question" for i in changes.items)


def test_openspec_requirements_match_by_name():
    change = ROOT / "examples/openspec/openspec/changes/add-invite-link-revocation"
    before, after = analysed(change), analysed(change)
    after.requirements[0].text = after.requirements[0].text.replace("issues a new link immediately", "issues a new link")
    items = compare(before, after, "x").items
    assert [(i.area, i.change, i.label) for i in items] == [("requirement", "changed", "Revoke invite link (albums)")]


# --- history -----------------------------------------------------------------------


def test_history_compares_with_the_previous_distinct_version(tmp_path):
    h = History(tmp_path)
    v1, v2 = analysed(V1), analysed(V2)
    assert h.record(v1) is None                     # first render: nothing to compare
    assert h.record(v1) is None                     # same spec again: still nothing
    previous, label = h.record(v2)                  # spec changed: compare with v1
    assert previous.documents == v1.documents and label.startswith("the previous version")
    previous, _ = h.record(v2)                      # re-render v2: still compared with v1
    assert previous.documents == v1.documents
    assert len(h.snapshots()) == 2


def test_history_keeps_a_bounded_number_of_snapshots(tmp_path):
    h = History(tmp_path)
    ir = analysed(V1)
    for n in range(KEEP + 3):
        ir.documents["spec.md"] += f"\n{n}"
        h.record(ir)
    assert len(h.snapshots()) == KEEP


# --- CLI ---------------------------------------------------------------------------


def _project(tmp_path, version):
    target = tmp_path / "specs/001-photo-albums"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(version, target)
    return target


def test_second_render_shows_what_changed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _project(tmp_path, V1)
    r = runner.invoke(app, ["review", str(spec), "--offline"])
    assert r.exit_code == 0 and "Changes since" not in r.output
    page = tmp_path / ".unboring/001-photo-albums/review.html"
    assert "What changed since" not in page.read_text()

    _project(tmp_path, V2)
    r = runner.invoke(app, ["review", str(spec), "--offline"])
    assert "Changes since the previous version" in r.output and "2 resolved" in r.output
    html = page.read_text()
    assert "What changed since the previous version" in html
    assert 'class="tag tag-chg-resolved">resolved' in html and "was at tasks.md:37" in html

    r = runner.invoke(app, ["review", str(spec), "--offline"])  # unchanged spec, same comparison
    assert "2 resolved" in r.output


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_since_a_git_ref(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _project(tmp_path, V1)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "v1")
    _project(tmp_path, V2)  # working tree now has v2; no previous render exists

    r = runner.invoke(app, ["review", str(spec), "--offline", "--since", "HEAD"])
    assert r.exit_code == 0, r.output
    assert "Changes since HEAD (" in r.output and "2 resolved" in r.output

    r = runner.invoke(app, ["review", str(spec), "--offline", "--since", "no-such-ref"])
    assert r.exit_code == 2 and "--since no-such-ref" in r.output


def test_since_outside_git_is_explained(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _project(tmp_path, V1)
    r = runner.invoke(app, ["review", str(spec), "--offline", "--since", "HEAD"])
    assert r.exit_code == 2 and "--since HEAD" in r.output


# --- page ------------------------------------------------------------------------


def test_page_lists_changes_by_area_and_escapes_them():
    after = analysed(V2)
    before = analysed(V1)
    before.requirements[3].text = "<b>old</b>"
    after.changes = compare(before, after, "the previous version")
    html = render_html(after)
    head = html.index("What changed since the previous version")
    assert head < html.index("Needs your judgment")  # at the top
    for label in ("Open questions", "Decisions", "Requirements", "User stories", "Data model", "Tasks"):
        assert f'<p class="change-area">{label}</p>' in html
    assert "<del>&lt;b&gt;old&lt;/b&gt;</del>" in html
    assert "spec.md +6 −5" in html


def test_page_says_when_nothing_changed():
    ir = analysed(V1)
    ir.changes = compare(analysed(V1), ir, "the previous version")
    assert "Nothing changed in substance" in render_html(ir)


def test_retitled_decision_matches_by_the_line_it_cites():
    before = _agent(V1)
    after = _agent(V2)  # v2 documents, v1 agent output: line numbers after line 59 moved by one
    d = next(x for x in after.decisions if x.sources[0].file == "research.md" and x.sources[0].line == 11)
    d.title, d.choice = "Expiring, revocable invite link", "One token per album that expires after 30 days."
    items = [i for i in compare(before, after, "x").items if i.area == "decision"]
    assert [(i.change, i.label) for i in items] == [("changed", "Expiring, revocable invite link")]
    assert items[0].before.startswith("Permanent invite link")


def test_line_map_follows_inserted_lines():
    from unboringspec.diff import line_map

    m = line_map({"a.md": "one\ntwo\nthree"}, {"a.md": "zero\none\nTWO\nthree"})
    assert m[("a.md", 1)] == 2 and m[("a.md", 2)] == 3 and m[("a.md", 3)] == 4
