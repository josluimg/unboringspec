"""Marks on the review page follow each item's identity, not its position (#29)."""

import json
import re
from pathlib import Path

from unboringspec.adapters import get_adapter
from unboringspec.insights import heuristic_insights
from unboringspec.render import render_html, review_keys

FIX = Path(__file__).parent / "fixtures/spec-kit/iterations"
V1, V2 = FIX / "v1/001-photo-albums", FIX / "v2/001-photo-albums"


def analysed(path):
    return heuristic_insights(get_adapter(path).load(path))


def by_text(ir):
    keys = review_keys(ir)
    out = {d.title: keys[d.id] for d in ir.decisions}
    out.update({q.question: keys[q.id] for q in ir.questions})
    return out


def test_unchanged_items_keep_their_key_even_when_renumbered():
    a, b = analysed(V1), analysed(V2)
    ka, kb = by_text(a), by_text(b)
    budget = "monthly storage budget per family"
    assert ka[budget] == kb[budget]
    q_ids = {q.question: q.id for q in a.questions}, {q.question: q.id for q in b.questions}
    assert q_ids[0][budget] != q_ids[1][budget]  # its position changed (Q4 -> Q2), its key did not
    assert ka["Upload path"] == kb["Upload path"]


def test_changed_or_resolved_items_get_a_new_key():
    ka, kb = by_text(analysed(V1)), by_text(analysed(V2))
    assert ka["Invite model"] != kb["Invite model"]  # same title, different decision
    assert ka["should links expire or be revocable?"] not in kb.values()  # resolved


def test_no_key_is_reused_for_a_different_item():
    ka = review_keys(analysed(V1))
    b = analysed(V2)
    kb = review_keys(b)
    texts_a = {v: k for k, v in ka.items()}
    a = analysed(V1)
    text_of = {**{d.id: f"{d.title}|{d.choice}" for d in a.decisions}, **{q.id: q.question for q in a.questions}}
    text_of_b = {**{d.id: f"{d.title}|{d.choice}" for d in b.decisions}, **{q.id: q.question for q in b.questions}}
    for item_id, key in kb.items():
        if key in texts_a:
            assert text_of[texts_a[key]] == text_of_b[item_id]


def test_line_shifts_do_not_change_keys():
    a = analysed(V1)
    shifted = analysed(V1)
    for q in shifted.questions:
        q.sources[0].line += 7
    assert review_keys(a) == review_keys(shifted)


def test_identical_items_stay_distinct():
    ir = analysed(V1)
    twin = ir.questions[0].model_copy(deep=True)
    twin.id = "Q99"
    ir.questions.append(twin)
    keys = review_keys(ir)
    assert keys[ir.questions[0].id] != keys["Q99"]


def test_page_uses_keys_and_drops_positional_state():
    html = render_html(analysed(V1))
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    keys = {d["id"]: d["key"] for d in data["decisions"]} | {q["id"]: q["key"] for q in data["questions"]}
    assert all(re.fullmatch(r"[dq]-[0-9a-f]{12}(-\d+)?", k) for k in keys.values())
    assert f'data-key="{keys["D1"]}"' in html and f'data-key="{keys["Q1"]}"' in html
    assert '"unboringspec:v2:" + data.feature' in html
    assert 'localStorage.removeItem("unboringspec:" + data.feature)' in html
    assert "card.dataset.key" in html
    assert "state[d.id]" not in html and "state[q.id]" not in html
