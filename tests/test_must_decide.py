"""The analysis's 'you must decide' list reaches the page and the export (#55)."""

import json
from pathlib import Path

from unboringspec.adapters import get_adapter
from unboringspec.insights import apply_insights, heuristic_insights, parse_insights
from unboringspec.render import calls_to_make, render_html

ROOT = Path(__file__).parent.parent
SPEC = ROOT / "examples/speckit/specs/001-photo-albums"
INSIGHTS = json.loads((ROOT / "schemas/examples/001-photo-albums.insights.json").read_text())


def agent_ir(must):
    data = dict(INSIGHTS, you_must_decide=must)
    ir, _ = apply_insights(get_adapter(SPEC).load(SPEC), parse_insights(json.dumps(data)), "agent")
    return ir


def payload(html):
    return json.loads(html.split('<script id="data" type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))


def test_the_list_is_shown_in_the_judgment_callout():
    must = ["Whether invite links expire", "Who owns the storage <budget>"]
    html = render_html(agent_ir(must))
    callout = html.split('<div class="callout">')[1].split("</div>")[0]
    assert "The calls this spec leaves to you:" in callout
    assert "<li>Whether invite links expire</li>" in callout
    assert "&lt;budget&gt;" in callout  # escaped like everything the agent writes


def test_the_list_reaches_the_export():
    html = render_html(agent_ir(["Whether invite links expire"]))
    assert payload(html)["must_decide"] == ["Whether invite links expire"]
    assert "data.must_decide.forEach" in html and payload(html)["ui"]["js_must_h"] == "Still to decide"


def test_items_already_shown_as_cards_are_not_repeated():
    ir = agent_ir([])
    question = ir.questions[0].question
    decision = ir.decisions[0]
    ir.summary.you_must_decide = [question, f"{decision.title}: {decision.choice}", "Something new"]
    assert calls_to_make(ir) == ["Something new"]


def test_offline_review_adds_nothing_new():
    ir = heuristic_insights(get_adapter(SPEC).load(SPEC))
    assert ir.summary.you_must_decide  # built from the questions and decide decisions...
    assert calls_to_make(ir) == []  # ...which are already cards
    assert 'class="must-decide"' not in render_html(ir)


def test_spanish_lead():
    html = render_html(agent_ir(["Si los enlaces caducan"]), lang="es")
    assert "Lo que esta spec deja en tus manos:" in html and payload(html)["ui"]["js_must_h"] == "Pendiente de decidir"
