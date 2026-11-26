"""An episode recorded for an earlier version of the spec is flagged, not silently replayed (#37)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec import tts
from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.history import documents_hash
from unboringspec.insights import heuristic_insights
from unboringspec.render import PODCAST_META, find_podcast, render_html, write_podcast_meta

ROOT = Path(__file__).parent.parent
FIX = ROOT / "tests/fixtures/spec-kit/iterations"
V1, V2 = FIX / "v1/001-photo-albums", FIX / "v2/001-photo-albums"
SCRIPT = ROOT / "schemas/examples/001-photo-albums.podcast.json"
runner = CliRunner()


class FakeEngine(tts.Engine):
    name = "fake"

    def check(self):
        pass

    def voices(self, lang):
        return {"guide": "g", "skeptic": "s"}

    def synth(self, text, voice, lang, speed, out):
        tts.write_wav(out, b"\x01\x00" * (tts.SAMPLE_RATE // 20))


def analysed(path):
    return heuristic_insights(get_adapter(path).load(path))


def episode(folder: Path, documents=None):
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, folder / "podcast.json")
    tts.write_wav(folder / "podcast.wav", b"\x00\x00" * 100)
    if documents is not None:
        write_podcast_meta(folder, documents)


def test_episode_of_this_version_is_current(tmp_path):
    ir = analysed(V1)
    episode(tmp_path, ir.documents)
    state = find_podcast(tmp_path, ir)
    assert state["stale"] is False and state["known_version"]
    html = render_html(ir, state)
    assert "stale-episode" not in html and "spec.md:" in html.split("Transcript")[1][:4000]


def test_episode_of_an_earlier_version_is_flagged_without_chips(tmp_path):
    episode(tmp_path, analysed(V1).documents)
    ir = analysed(V2)
    state = find_podcast(tmp_path, ir)
    assert state["stale"] and state["known_version"] and state["changes"] is None  # no snapshot to count from
    html = render_html(ir, state)
    assert "This episode is about an earlier version of the spec." in html
    transcript = html.split("<summary>Transcript</summary>")[1].split("</details>")[0]
    assert 'class="src"' not in transcript  # line links would point at the wrong text


def test_changes_are_counted_when_the_old_version_is_in_history(tmp_path):
    from unboringspec.history import History

    v1 = analysed(V1)
    History(tmp_path).record(v1)
    episode(tmp_path, v1.documents)
    state = find_podcast(tmp_path, analysed(V2))
    assert state["changes"] == 11
    assert "(11 changes since)" in render_html(analysed(V2), state)


def test_episode_without_a_version_is_treated_as_earlier(tmp_path):
    episode(tmp_path)  # recorded before this fix: no podcast.meta.json
    ir = analysed(V1)
    state = find_podcast(tmp_path, ir)
    assert state["stale"] and not state["known_version"]
    assert "recorded before episodes carried their version" in render_html(ir, state)


def test_podcast_render_records_the_version_and_render_warns_later(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(tts.ENGINES, "fake", FakeEngine)
    spec = tmp_path / "specs/001-photo-albums"
    shutil.copytree(V1, spec)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    shutil.copy(SCRIPT, wd / "podcast.json")

    r = runner.invoke(app, ["podcast", "render", str(spec), "--engine", "fake"])
    assert r.exit_code == 0, r.output
    meta = json.loads((wd / PODCAST_META).read_text())
    assert meta["version"] == documents_hash(get_adapter(spec).load(spec).documents) and meta["engine"] == "fake"
    assert "stale-episode" not in (wd / "review.html").read_text()

    r = runner.invoke(app, ["review", str(spec), "--offline"])  # same spec: no warning
    assert "earlier version" not in r.output

    shutil.rmtree(spec)
    shutil.copytree(V2, spec)  # the spec changes
    r = runner.invoke(app, ["review", str(spec), "--offline"])
    assert "The podcast on this page is about an earlier version of the spec (11 changes since)" in r.output
    assert "/unboring-podcast 001-photo-albums" in r.output
    assert "stale-episode" in (wd / "review.html").read_text()
