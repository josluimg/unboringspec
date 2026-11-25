import json
import shutil
import wave
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from unboringspec import tts
from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.integrations import INTEGRATIONS, SKILLS, render_integration
from unboringspec.podcast import (
    PODCAST_SCHEMA_ID,
    PODCAST_SCHEMA_VERSION,
    PodcastScript,
    build_podcast_prompt,
    parse_script,
    podcast_json_schema,
    validate_script,
)

ROOT = Path(__file__).parent.parent
EXAMPLE_SPEC = ROOT / "examples/speckit/specs/001-photo-albums"
EXAMPLE_SCRIPT = ROOT / "schemas/examples/001-photo-albums.podcast.json"
PUBLISHED = ROOT / f"schemas/podcast.v{PODCAST_SCHEMA_VERSION}.schema.json"
runner = CliRunner()


def docs():
    return get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC).documents


def script(**over) -> dict:
    data = {
        "title": "Test",
        "language": "es",
        "hosts": [{"id": "A", "name": "Lucía", "role": "guide"}, {"id": "B", "name": "Álex", "role": "skeptic"}],
        "turns": [
            {"speaker": "A", "text": "Hola.", "sources": [{"file": "spec.md", "line": 6}]},
            {"speaker": "B", "text": "Una   cita\n inventada.", "sources": [{"file": "spec.md", "line": 9999}]},
            {"speaker": "A", "text": "   "},
        ],
    }
    data.update(over)
    return data


# --- contract --------------------------------------------------------------------


def test_published_schema_matches_model():
    published = json.loads(PUBLISHED.read_text())
    assert published == podcast_json_schema(), f"Regenerate with: unboring schema podcast > {PUBLISHED.relative_to(ROOT)}"
    assert published["$id"] == PODCAST_SCHEMA_ID
    jsonschema.Draft202012Validator.check_schema(published)


def test_example_script_is_valid_and_fully_cited():
    jsonschema.validate(json.loads(EXAMPLE_SCRIPT.read_text()), json.loads(PUBLISHED.read_text()))
    turns, problems = validate_script(parse_script(EXAMPLE_SCRIPT.read_text()), docs())
    assert problems == []
    assert len(turns) > 30


def test_validate_script_reports_and_cleans():
    turns, problems = validate_script(PodcastScript.model_validate(script()), docs())
    assert [t.text for t in turns] == ["Hola.", "Una cita inventada."]
    assert turns[0].role == "guide" and turns[1].name == "Álex"
    assert turns[1].sources == []
    assert any("do not exist" in p for p in problems)
    assert any("empty" in p for p in problems)


def test_validate_script_needs_guide_and_skeptic():
    bad = script(hosts=[{"id": "A", "name": "X", "role": "guide"}, {"id": "B", "name": "Y", "role": "guide"}])
    with pytest.raises(ValueError, match="skeptic"):
        validate_script(PodcastScript.model_validate(bad), docs())


def test_prompt_uses_insights_when_available():
    ir = get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC)
    with_insights = build_podcast_prompt(ir, '{"one_liner": "x"}', "es")
    assert "Review analysis already done" in with_insights
    assert "write in es" in with_insights
    assert "===== FILE: spec.md =====" in with_insights
    assert "Review analysis already done" not in build_podcast_prompt(ir)


# --- audio -----------------------------------------------------------------------


class FakeEngine(tts.Engine):
    name = "fake"

    def check(self):
        pass

    def voices(self, lang):
        return {"guide": "g", "skeptic": "s"}

    def synth(self, text, voice, lang, speed, out):
        tts.write_wav(out, b"\x01\x00" * (tts.SAMPLE_RATE // 10))  # 0.1 s per turn


def test_assemble_without_ffmpeg_writes_exact_wav(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    parts = []
    for i in range(3):
        p = tmp_path / f"{i}.wav"
        FakeEngine().synth("x", "g", "es", 1.0, p)
        parts.append(p)
    out = tts.assemble(parts, tmp_path / "podcast", pause_ms=200)
    assert out.suffix == ".wav"
    with wave.open(str(out)) as w:
        assert w.getframerate() == tts.SAMPLE_RATE
        assert w.getnframes() == 3 * tts.SAMPLE_RATE // 10 + 2 * tts.SAMPLE_RATE * 200 // 1000


def test_podcast_render_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(tts.ENGINES, "fake", FakeEngine)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    (wd / "podcast.json").write_text(EXAMPLE_SCRIPT.read_text())

    r = runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "fake"])
    assert r.exit_code == 0, r.output
    audio = next(wd.glob("podcast.*[3v]"))  # mp3 with ffmpeg, wav without
    assert audio.stat().st_size > 0
    assert "**Lucía:**" in (wd / "podcast.md").read_text()
    html = (wd / "review.html").read_text()
    assert f'src="{audio.name}"' in html and "Álbumes familiares" in html


def test_podcast_render_rejects_bad_cast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    bad = script(hosts=[{"id": "A", "name": "X", "role": "guide"}])
    (wd / "podcast.json").write_text(json.dumps(bad))
    r = runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "say"])
    assert r.exit_code == 1
    assert "not a valid podcast script" in r.output


def test_unknown_engine_is_explained():
    with pytest.raises(tts.EngineUnavailable, match="Available"):
        tts.pick_engine("nope")


def test_say_voice_choice_prefers_two_distinct_voices(monkeypatch):
    engine = tts.SayEngine()
    monkeypatch.setattr(engine, "_installed", lambda: [("Mónica", "es_ES"), ("Paulina", "es_MX"), ("Samantha", "en_US")])
    assert engine.voices("es") == {"guide": "Mónica", "skeptic": "Paulina"}
    with pytest.raises(tts.EngineUnavailable):
        engine.voices("de")


def test_kokoro_voices_cover_spanish_and_fallback():
    k = tts.KokoroEngine()
    assert k.voices("es-ES") == {"guide": "ef_dora", "skeptic": "em_alex"}
    assert k.voices("xx") == tts.KOKORO_VOICES["en"]


# --- skills ----------------------------------------------------------------------


def test_init_skips_podcast_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "--ai", "claude", "--ai", "gemini"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".claude/skills/unboring-review/SKILL.md").exists()
    assert not (tmp_path / ".claude/skills/unboring-podcast").exists()
    assert not (tmp_path / ".gemini/commands/unboring.podcast.toml").exists()
    assert "unboring init --ai claude --ai gemini --podcast" in r.output


def test_init_podcast_can_be_added_later(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init", "--ai", "claude"])
    review = tmp_path / ".claude/skills/unboring-review/SKILL.md"
    review.write_text("customised")
    r = runner.invoke(app, ["init", "--ai", "claude", "--podcast"])
    assert r.exit_code == 0, r.output
    assert review.read_text() == "customised"  # existing skill untouched
    assert (tmp_path / ".claude/skills/unboring-podcast/SKILL.md").exists()


def test_init_installs_both_skills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "--ai", "claude", "--ai", "gemini", "--podcast"])
    assert r.exit_code == 0, r.output
    podcast = (tmp_path / ".claude/skills/unboring-podcast/SKILL.md").read_text()
    assert "name: unboring-podcast" in podcast and "unboring podcast render" in podcast
    assert "allowed-tools: Bash(unboring:*)" in podcast
    assert (tmp_path / ".gemini/commands/unboring.podcast.toml").exists()
    assert (tmp_path / ".gemini/commands/unboring.review.toml").exists()


def test_every_integration_renders_every_skill():
    for integ in INTEGRATIONS.values():
        for skill in SKILLS.values():
            assert "unboring" in render_integration(integ, skill)


def test_schema_command_podcast():
    r = runner.invoke(app, ["schema", "podcast"])
    assert r.exit_code == 0
    assert json.loads(r.output) == json.loads(PUBLISHED.read_text())


# --- tones -----------------------------------------------------------------------

from unboringspec.podcast import DEFAULT_TONE, TONES, resolve_tone, tone_speed  # noqa: E402


def test_every_preset_tone_is_complete():
    assert DEFAULT_TONE in TONES
    for t in TONES.values():
        assert t.summary and len(t.style) > 60 and 0.5 <= t.speed <= 2.0


def test_resolve_tone_preset_custom_and_default():
    assert resolve_tone(None)[0] == "casual"
    assert resolve_tone("ROAST")[0] == "roast"
    tone_id, style, speed = resolve_tone("como dos piratas discutiendo un mapa")
    assert tone_id == "custom" and "piratas" in style and speed == 1.0
    with pytest.raises(ValueError):
        resolve_tone("x" * 400)


def test_prompt_carries_tone_and_keeps_the_guardrails():
    ir = get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC)
    roast = build_podcast_prompt(ir, None, "es", "roast")
    assert TONES["roast"].style in roast
    assert 'Set "tone" in the output to "roast"' in roast
    assert "nobody real is mocked" in roast
    custom = build_podcast_prompt(ir, None, "es", "narrado como un partido de pádel")
    assert "partido de pádel" in custom and '"custom"' in custom


def test_render_uses_tone_speed_and_shows_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    speeds = []

    class SpeedSpy(FakeEngine):
        def synth(self, text, voice, lang, speed, out):
            speeds.append(speed)
            super().synth(text, voice, lang, speed, out)

    monkeypatch.setitem(tts.ENGINES, "spy", SpeedSpy)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    data = json.loads(EXAMPLE_SCRIPT.read_text())
    data["tone"] = "sports"
    (wd / "podcast.json").write_text(json.dumps(data))
    r = runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "spy"])
    assert r.exit_code == 0, r.output
    assert set(speeds) == {tone_speed("sports")} == {1.1}
    assert "Sports commentary" in (wd / "review.html").read_text()

    speeds.clear()
    runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "spy", "--speed", "0.8"])
    assert set(speeds) == {0.8}


def test_prompt_command_reports_tone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["podcast", "prompt", str(EXAMPLE_SPEC), "--tone", "noir"])
    assert r.exit_code == 0 and "Tone:     noir" in r.output
    r = runner.invoke(app, ["podcast", "prompt", str(EXAMPLE_SPEC), "--tone", "y" * 400])
    assert r.exit_code == 2


def test_tones_command_lists_presets():
    r = runner.invoke(app, ["podcast", "tones"])
    assert r.exit_code == 0
    for t in TONES:
        assert t in r.output
