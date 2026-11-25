"""Bringing a review back and following it up on the next iteration (#28)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.feedback import ReviewError, ReviewItem, SavedReview, follow_up, latest_review, parse_review, save_review
from unboringspec.history import History, documents_hash
from unboringspec.insights import heuristic_insights
from unboringspec.integrations import skill_body
from unboringspec.render import render_html, review_keys

FIX = Path(__file__).parent / "fixtures/spec-kit/iterations"
V1, V2 = FIX / "v1/001-photo-albums", FIX / "v2/001-photo-albums"
LINKS, BUDGET = "should links expire or be revocable?", "monthly storage budget per family"
runner = CliRunner()


def analysed(path):
    return heuristic_insights(get_adapter(path).load(path))


def review_of(ir, marks):
    """marks: list of (kind, title or question, extra) as the page would export them."""
    keys = review_keys(ir)
    items = []
    for kind, text, extra in marks:
        if kind == "answer":
            q = next(q for q in ir.questions if q.question == text)
            items.append(ReviewItem(id=q.id, key=keys[q.id], kind="answer", text=text, answer=extra))
        else:
            d = next(d for d in ir.decisions if d.title == text)
            items.append(ReviewItem(id=d.id, key=keys[d.id], kind=kind, text=text, choice=d.choice, note=extra))
    return SavedReview(version=documents_hash(ir.documents), feature=ir.feature, items=items)


def as_markdown(review: SavedReview) -> str:
    """What the page's buildReview() produces: '--' written as -\\u002d inside the comment."""
    block = json.dumps(review.model_dump()).replace("--", "-\\u002d")
    return f"# Review: {review.feature}\n\n## Approved\n\n- ...\n<!-- unboring:review {block} -->\n"


@pytest.fixture
def history(tmp_path):
    h = History(tmp_path)
    h.record(analysed(V1))
    return h


# --- format ------------------------------------------------------------------------


def test_block_round_trip_survives_comment_breakers():
    v1 = analysed(V1)
    review = review_of(v1, [("question", "Invite model", "no -- really --> make it revocable")])
    parsed = parse_review(as_markdown(review))
    assert parsed.items[0].note == "no -- really --> make it revocable"
    assert parsed.version == documents_hash(v1.documents)


def test_review_without_block_is_explained():
    with pytest.raises(ReviewError, match="Export the review again"):
        parse_review("# Review: old export\n\n## Approved\n")


def test_latest_review_wins(tmp_path):
    v1 = analysed(V1)
    save_review(tmp_path, as_markdown(review_of(v1, [("approve", "Upload path", "")])))
    save_review(tmp_path, as_markdown(review_of(v1, [("approve", "HEIC support", "")])))
    _, latest = latest_review(tmp_path)
    assert latest.items[0].text == "HEIC support"


# --- follow-up ---------------------------------------------------------------------


def outcomes(fu):
    return {(i.kind, i.label): i.outcome for i in fu.items}


def test_follow_up_of_v1_review_on_v2(history):
    v1, v2 = analysed(V1), analysed(V2)
    review = review_of(v1, [
        ("answer", LINKS, "Revocable, 90 days"),
        ("answer", BUDGET, "10 GB"),
        ("approve", "Upload path", ""),
        ("question", "Invite model", "make it revocable"),
        ("question", "Digest delivery", "half-hour timezones?"),
    ])
    fu = follow_up(review, "2026-11-25 10:00", v2, history)
    assert outcomes(fu) == {
        ("answer", LINKS): "addressed",                  # resolved in v2
        ("answer", BUDGET): "pending",                   # still open: answer kept
        ("approve", "Upload path"): "approved",          # unchanged: still approved
        ("question", "Invite model"): "changed",         # changed: check it matches the note
        ("question", "Digest delivery"): "not-addressed",
    }
    keys = {v: k for k, v in review_keys(v2).items()}
    by_title = {d.title: d.id for d in v2.decisions} | {q.question: q.id for q in v2.questions}
    k = lambda t: review_keys(v2)[by_title[t]]
    assert fu.carried == {
        k(BUDGET): {"answer": "10 GB"},
        k("Upload path"): {"v": "approve"},
        k("Digest delivery"): {"v": "question", "note": "half-hour timezones?"},
    }
    assert "make it revocable" in fu.flags[k("Invite model")]
    assert k("Invite model") not in fu.carried  # its content changed: no stale mark
    assert keys  # keys exist for every current item


def test_approved_then_changed_is_flagged(history):
    v1, v2 = analysed(V1), analysed(V2)
    fu = follow_up(review_of(v1, [("approve", "Invite model", "")]), "x", v2, history)
    assert outcomes(fu) == {("approve", "Invite model"): "approved-changed"}
    assert fu.carried == {} and "Look again" in next(iter(fu.flags.values()))


def test_removed_decision(history):
    v1, v2 = analysed(V1), analysed(V2)
    v2.decisions = [d for d in v2.decisions if d.title != "HEIC support"]
    fu = follow_up(review_of(v1, [("approve", "HEIC support", "")]), "x", v2, history)
    assert outcomes(fu) == {("approve", "HEIC support"): "removed"}


def test_review_of_this_very_version_just_carries_over(history):
    v1 = analysed(V1)
    review = review_of(v1, [("answer", LINKS, "Revocable"), ("question", "Invite model", "why?"), ("approve", "Upload path", "")])
    fu = follow_up(review, "x", analysed(V1), history)
    assert fu.same_version and fu.items == [] and fu.flags == {}
    assert sorted(m.get("v", "answer") for m in fu.carried.values()) == ["answer", "approve", "question"]


def test_without_the_reviewed_snapshot_titles_still_match(tmp_path):
    v1, v2 = analysed(V1), analysed(V2)
    fu = follow_up(review_of(v1, [("question", "Invite model", "n"), ("answer", LINKS, "a")]), "x", v2, History(tmp_path))
    assert outcomes(fu) == {("question", "Invite model"): "changed", ("answer", LINKS): "addressed"}
    assert any("matched by title" in n for n in fu.notes)


# --- CLI and page ------------------------------------------------------------------


def _project(tmp_path, version):
    target = tmp_path / "specs/001-photo-albums"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(version, target)
    return target


def test_end_to_end_review_feedback_next_iteration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _project(tmp_path, V1)
    assert runner.invoke(app, ["review", str(spec), "--offline"]).exit_code == 0

    review = review_of(analysed(spec), [("answer", BUDGET, "10 GB"), ("approve", "Invite model", ""), ("approve", "Upload path", "")])
    path = tmp_path / "Downloads-review.md"
    path.write_text(as_markdown(review))
    r = runner.invoke(app, ["feedback", str(spec), str(path)])
    assert r.exit_code == 0 and "3 points on this version" in r.output

    _project(tmp_path, V2)
    r = runner.invoke(app, ["review", str(spec), "--offline"])
    assert "Follow-up of your review of" in r.output
    html = (tmp_path / ".unboring/001-photo-albums/review.html").read_text()
    assert "Your last review" in html
    assert "Approved, then changed: look again" in html and "Answered, still open in the spec" in html
    assert "1 approval still holds: Upload path" in html
    data = json.loads(html.split('<script id="data" type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert sorted(m.get("v", "answer") for m in data["carried"].values()) == ["answer", "approve"]
    assert data["version"] == documents_hash(analysed(spec).documents)
    assert '<p class="flag">You approved this before; it has changed since. Look again.</p>' in html


def test_feedback_from_stdin_and_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _project(tmp_path, V1)
    text = as_markdown(review_of(analysed(spec), [("approve", "Upload path", "")]))
    r = runner.invoke(app, ["feedback", str(spec), "-"], input=text)
    assert r.exit_code == 0 and (tmp_path / ".unboring/001-photo-albums/reviews").is_dir()
    r = runner.invoke(app, ["feedback", str(spec), "-"], input="# Review\nno block\n")
    assert r.exit_code == 1 and "Export the review again" in r.output


def test_page_has_copy_button_and_review_block_builder():
    html = render_html(analysed(V1))
    assert 'id="copy"' in html and "Copy for your agent" in html
    assert "unboring:review ${block}" in html and '"version":' in html.split('id="data"')[1][:20000]


def test_skill_saves_shared_reviews():
    body = skill_body("unboring-review")
    assert "unboring feedback <folder>" in body and "keep it intact" in body
