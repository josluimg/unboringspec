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

    def synth(self, text, voice, lang, speed, out, terms=()):
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

from unboringspec.podcast import BASE_SPEED, DEFAULT_TONE, TONES, resolve_tone, tone_speed  # noqa: E402


def test_every_preset_tone_is_complete():
    assert DEFAULT_TONE in TONES
    for t in TONES.values():
        assert t.summary and len(t.style) > 60 and 0.5 <= t.speed <= 2.0


def test_resolve_tone_preset_custom_and_default():
    assert resolve_tone(None)[0] == "casual"
    assert resolve_tone("ROAST")[0] == "roast"
    tone_id, style, speed = resolve_tone("como dos piratas discutiendo un mapa")
    assert tone_id == "custom" and "piratas" in style and speed == BASE_SPEED == 1.2
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
        def synth(self, text, voice, lang, speed, out, terms=()):
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
    assert set(speeds) == {tone_speed("sports")} == {1.32}  # 1.2 base x sports pace 1.1
    assert "Retransmisión deportiva" in (wd / "review.html").read_text()  # Spanish script → Spanish page

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


# --- #57: terms said in their own language, base speed, the player ------------------


def test_split_by_language_whole_words_case_and_longest_first():
    split = tts.split_by_language
    terms = [("Snowflake", "en"), ("Control-M", "en"), ("Control", "en")]
    assert split("Borra los ficheros de snowflake y lo lanza Control-M.", terms) == [
        ("Borra los ficheros de ", None), ("snowflake", "en"), (" y lo lanza ", None), ("Control-M", "en"), (".", None),
    ]
    assert split("Snowflakes no es un término", terms) == [("Snowflakes no es un término", None)]  # whole words only
    assert split("Sin términos", []) == [("Sin términos", None)]


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def phonemize(self, text, lang="en-us", norm=True):
        self.calls.append((text, lang))
        return f"[{lang}:{text.strip()}]" if text.strip(" ,.") else text.strip()


class FakeKokoro:
    def __init__(self):
        self.tokenizer = FakeTokenizer()
        self.created = []

    def create(self, text, voice, speed=1.0, lang="en-us", is_phonemes=False):
        self.created.append((text, lang, is_phonemes))
        import numpy as np

        return np.zeros(240, dtype="float32"), tts.SAMPLE_RATE


def test_kokoro_says_listed_terms_with_their_own_language(tmp_path):
    pytest.importorskip("numpy")
    engine = tts.KokoroEngine()
    engine._model = FakeKokoro()
    engine.synth("Los ficheros de Snowflake los lanza Control-M.", "ef_dora", "es", 1.2, tmp_path / "a.wav",
                 terms=[("Snowflake", "en"), ("Control-M", "en")])
    assert ("Snowflake", "en-us") in engine._model.tokenizer.calls
    assert ("Control M", "en-us") in engine._model.tokenizer.calls  # hyphen read as a space, not "minus"
    assert ("Los ficheros de ", "es") in engine._model.tokenizer.calls
    text, lang, is_phonemes = engine._model.created[0]
    assert is_phonemes and lang == "es" and "[en-us:Snowflake]" in text

    engine._model = FakeKokoro()  # no terms in the turn: plain text, as before
    engine.synth("Nada en inglés.", "ef_dora", "es", 1.2, tmp_path / "b.wav", terms=[("Snowflake", "en")])
    assert engine._model.created[0] == ("Nada en inglés.", "es", False)


def test_terms_are_optional_in_the_contract():
    assert parse_script(json.dumps(script())).terms == []
    parsed = parse_script(json.dumps(script(terms=[{"text": "Snowflake", "lang": "en"}])))
    assert parsed.terms[0].text == "Snowflake"
    jsonschema.validate(script(terms=[{"text": "endpoint", "lang": "en"}]), json.loads(PUBLISHED.read_text()))


def test_prompt_keeps_jargon_and_says_especificacion():
    prompt = build_podcast_prompt(get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC), None, "es", None)
    assert "la especificación" in prompt and 'never say "spec" outside English' in prompt
    assert "Keep technical jargon" in prompt and 'List in "terms"' in prompt


def test_render_passes_terms_to_the_engine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = []

    class TermsSpy(FakeEngine):
        def synth(self, text, voice, lang, speed, out, terms=()):
            seen.append(list(terms))
            super().synth(text, voice, lang, speed, out)

    monkeypatch.setitem(tts.ENGINES, "spy", TermsSpy)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    data = json.loads(EXAMPLE_SCRIPT.read_text())
    data["terms"] = [{"text": "HEIC", "lang": "en"}]
    (wd / "podcast.json").write_text(json.dumps(data))
    r = runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "spy"])
    assert r.exit_code == 0, r.output
    assert seen and all(t == [("HEIC", "en")] for t in seen)


def test_every_tone_is_relative_to_the_base_speed():
    assert TONES["casual"].speed == BASE_SPEED == 1.2
    assert TONES["noir"].speed < BASE_SPEED < TONES["sports"].speed


def test_player_with_visible_speed_and_native_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(tts.ENGINES, "fake", FakeEngine)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    shutil.copy(EXAMPLE_SCRIPT, wd / "podcast.json")  # a Spanish script
    assert runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "fake"]).exit_code == 0
    html = (wd / "review.html").read_text()
    player = html.split('<div class="player"')[1].split("<audio")[0]
    assert 'aria-label="Reproductor del episodio"' in html
    assert [b for b in ("1×", "1,25×", "1,5×", "2×") if b in player] == ["1×", "1,25×", "1,5×", "2×"]
    assert '<audio controls preload="metadata"' in html  # the native player stays, for pages without JavaScript
    assert "html:not(.js) .player { display: none; }" in html and "html.js .listen audio { display: none; }" in html
    assert 'localStorage.setItem("unboring-speed"' in html


# --- #59: seeking that keeps playing ------------------------------------------------


def test_episodes_are_encoded_at_a_constant_bitrate(tmp_path, monkeypatch):
    """VBR makes browsers guess byte offsets when seeking, and WebKit can stall on it."""
    calls = []
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(tts.subprocess, "run", lambda args, **kw: calls.append(args))
    part = tmp_path / "1.wav"
    FakeEngine().synth("x", "g", "es", 1.0, part)
    tts.assemble([part], tmp_path / "podcast")
    args = calls[-1]
    assert args[args.index("-b:a") + 1] == "64k" and "-q:a" not in args


def test_player_seeks_on_release_and_recovers_a_stall(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(tts.ENGINES, "fake", FakeEngine)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    shutil.copy(EXAMPLE_SCRIPT, wd / "podcast.json")
    assert runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "fake"]).exit_code == 0
    html = (wd / "review.html").read_text()
    script = html.split("// Podcast player (#57)")[1].split('document.getElementById("copy")')[0]
    assert 'seek.addEventListener("pointerdown"' in script and "window.addEventListener(\"pointerup\", release)" in script
    assert "if (!dragging) seekTo(" in script  # keyboard steps seek right away, drags only on release
    assert 'audio.addEventListener("waiting"' in script and "audio.load()" in script
    assert "audio.readyState >= 3" in script  # never reloads audio that has data to play


# --- #61: a cast of voices, blends and pitch ------------------------------------------


def test_voice_specs():
    assert tts.parse_voice("em_alex") == ([("em_alex", 1.0)], 0.0)
    assert tts.parse_voice("em_alex@-2") == ([("em_alex", 1.0)], -2.0)
    blend, shift = tts.parse_voice("ef_dora*3 + em_alex @ +1.5")
    assert blend == [("ef_dora", 0.75), ("em_alex", 0.25)] and shift == 1.5
    for bad in ("", "Alex", "em_alex*0", "em_alex*x", "em_alex@-9"):
        with pytest.raises(ValueError):
            tts.parse_voice(bad)


def test_every_voice_in_the_cast_parses_and_roles_stay_apart():
    for lang, pool in tts.KOKORO_CAST.items():
        for role in ("guide", "skeptic"):
            for spec in pool[role]:
                tts.parse_voice(spec)
        assert pool["guide"][0] == tts.KOKORO_VOICES[lang]["guide"]  # the default pair is in the cast
        assert pool["skeptic"][0] == tts.KOKORO_VOICES[lang]["skeptic"]


def test_cast_picks_at_random_and_drops_pitch_without_ffmpeg(monkeypatch):
    import random

    engine = tts.KokoroEngine()
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    picks = {tuple(engine.cast("es", random.Random(seed)).items()) for seed in range(60)}
    assert len(picks) > 6  # many pairs, not always the same
    for pair in picks:
        guide, skeptic = dict(pair)["guide"], dict(pair)["skeptic"]
        assert guide in tts.KOKORO_CAST["es"]["guide"] and skeptic in tts.KOKORO_CAST["es"]["skeptic"]
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert all("@" not in engine.cast("es", random.Random(s))["skeptic"] for s in range(60))
    assert engine.cast("fr") == tts.KOKORO_VOICES["fr"]  # no cast yet: the default pair


class BlendKokoro(FakeKokoro):
    def get_voices(self):
        return ["ef_dora", "em_alex", "em_santa"]

    def get_voice_style(self, name):
        import numpy as np

        return np.full((2, 2), {"ef_dora": 1.0, "em_alex": 3.0, "em_santa": 5.0}[name], dtype="float32")

    def create(self, text, voice, speed=1.0, lang="en-us", is_phonemes=False):
        self.voice = voice
        return super().create(text, voice, speed, lang, is_phonemes)


def test_kokoro_blends_styles_and_shifts_pitch(tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    engine = tts.KokoroEngine()
    engine._model = BlendKokoro()
    shifted = []
    monkeypatch.setattr(tts, "shift_pitch", lambda path, semitones: shifted.append(semitones))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    engine.synth("Hola.", "em_alex*0.5+em_santa*0.5@-2", "es", 1.2, tmp_path / "a.wav")
    assert float(engine._model.voice[0][0]) == 4.0  # halfway between 3 and 5
    assert shifted == [-2.0]
    engine.synth("Hola.", "ef_dora", "es", 1.2, tmp_path / "b.wav")
    assert engine._model.voice == "ef_dora"  # a plain voice is passed by name
    with pytest.raises(tts.EngineUnavailable):
        engine.synth("Hola.", "em_nobody", "es", 1.2, tmp_path / "c.wav")


def test_render_records_the_voices_it_used(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(tts.ENGINES, "fake", FakeEngine)
    wd = tmp_path / ".unboring/001-photo-albums"
    wd.mkdir(parents=True)
    shutil.copy(EXAMPLE_SCRIPT, wd / "podcast.json")
    r = runner.invoke(app, ["podcast", "render", str(EXAMPLE_SPEC), "--engine", "fake", "--voice-skeptic", "x_y"])
    assert r.exit_code == 0, r.output
    meta = json.loads((wd / "podcast.meta.json").read_text())
    assert meta["voices"] == {"guide": "g", "skeptic": "x_y"}
