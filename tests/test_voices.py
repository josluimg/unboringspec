"""Voice engines across operating systems. Windows and Linux are tested by mocking the OS
commands they call, since CI and contributors may not have every platform at hand."""

import base64
import subprocess
import sys
import wave

import pytest
from typer.testing import CliRunner

from unboringspec import tts
from unboringspec.cli import app

runner = CliRunner()


# --- choosing two distinct hosts ---------------------------------------------------


def test_pick_two_prefers_female_guide_and_male_skeptic():
    assert tts._pick_two([("M1", "male"), ("F1", "female"), ("M2", "male")]) == {"guide": "F1", "skeptic": "M1"}


def test_pick_two_with_one_voice_pitches_the_skeptic_down():
    """Windows often has only Helena in Spanish: the skeptic is Helena, lower (#66)."""
    assert tts._pick_two([("Microsoft Helena Desktop", "female")]) == {
        "guide": "Microsoft Helena Desktop",
        "skeptic": "Microsoft Helena Desktop@-3",
    }


def test_split_shift():
    assert tts.split_shift("Microsoft Helena Desktop@-3") == ("Microsoft Helena Desktop", -3.0)
    assert tts.split_shift("Mónica") == ("Mónica", 0.0)
    assert tts.split_shift("Helena@-40") == ("Helena", -6.0)  # capped


def capture_powershell(monkeypatch):
    scripts = []
    monkeypatch.setattr(tts, "_powershell", lambda script: scripts.append(script) or subprocess.CompletedProcess([], 0, "", ""))
    return scripts


def test_sapi_lowers_the_pitch_with_ffmpeg(tmp_path, monkeypatch):
    scripts = capture_powershell(monkeypatch)
    shifted = []
    monkeypatch.setattr(tts.shutil, "which", lambda name: "ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(tts, "shift_pitch", lambda path, semitones: shifted.append(semitones))
    tts.SapiEngine().synth("Hola", "Microsoft Helena Desktop@-3", "es", 1.2, tmp_path / "a.wav")
    assert "SelectVoice('Microsoft Helena Desktop')" in scripts[0] and "$s.Speak($t)" in scripts[0]
    assert shifted == [-3.0]


def test_sapi_lowers_the_pitch_through_ssml_without_ffmpeg(tmp_path, monkeypatch):
    scripts = capture_powershell(monkeypatch)
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    tts.SapiEngine().synth("<b>Hola</b> & adiós", "Microsoft Helena Desktop@-3", "es", 1.2, tmp_path / "a.wav")
    script = scripts[0]
    assert "SpeakSsml" in script and "<prosody pitch='low'>" in script
    assert "SecurityElement]::Escape($t)" in script  # the turn's text is escaped inside the SSML
    tts.SapiEngine().synth("Hola", "Microsoft Helena Desktop", "es", 1.2, tmp_path / "b.wav")
    assert "SpeakSsml" not in scripts[1]  # the guide keeps her own voice


def test_espeak_uses_its_own_pitch_without_ffmpeg(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tts.subprocess, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(tts, "normalize_wav", lambda path: None)
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name.startswith("espeak") else None)
    tts.EspeakEngine().synth("Hola", "es@-3", "es", 1.2, tmp_path / "a.wav")
    args = calls[0]
    assert args[args.index("-v") + 1] == "es" and args[args.index("-p") + 1] == "35"


def test_pick_two_without_gender_uses_two_different_voices():
    assert tts._pick_two([("A", ""), ("B", "")]) == {"guide": "A", "skeptic": "B"}


# --- engine selection per OS -------------------------------------------------------


@pytest.mark.parametrize("platform,expected", [("darwin", "say"), ("win32", "sapi"), ("linux", "espeak")])
def test_system_engine_per_os(monkeypatch, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    assert tts.system_engine_name() == expected


def test_auto_falls_back_to_system_with_reasons(monkeypatch):
    monkeypatch.setattr(tts.KokoroEngine, "package_installed", lambda self: False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(tts.shutil, "which", lambda _: None)
    with pytest.raises(tts.EngineUnavailable) as e:
        tts.pick_engine("auto")
    assert "kokoro" in str(e.value) and "apt install espeak-ng" in str(e.value)


# --- Kokoro install hints ------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix,version,expected",
    [
        ("/Users/x/.local/share/uv/tools/unboringspec", (3, 14, 0), "uv tool install --python 3.12 --reinstall"),
        ("C:/Users/x/AppData/Roaming/uv/tools/unboringspec", (3, 12, 0), "uv tool install --python 3.12 --reinstall"),
        ("/Users/x/.local/pipx/venvs/unboringspec", (3, 12, 0), "pipx inject unboringspec kokoro-onnx numpy"),
        ("/Users/x/.local/pipx/venvs/unboringspec", (3, 14, 0), "pipx install --force --python python3.12"),
        ("/home/x/project/.venv", (3, 12, 0), "-m pip install"),
        ("/home/x/project/.venv", (3, 14, 0), "uv tool install --python 3.12"),
    ],
)
def test_kokoro_install_hint_matches_how_it_was_installed(monkeypatch, prefix, version, expected):
    monkeypatch.setattr(sys, "prefix", prefix)
    monkeypatch.setattr(sys, "version_info", version)
    assert expected in tts.kokoro_install_hint()


def test_kokoro_check_explains_missing_model(monkeypatch, tmp_path):
    monkeypatch.setattr(tts.KokoroEngine, "package_installed", lambda self: True)
    monkeypatch.setenv("UNBORING_KOKORO_DIR", str(tmp_path))
    with pytest.raises(tts.EngineUnavailable) as e:
        tts.KokoroEngine().check()
    assert e.value.fix == "unboring podcast setup"


# --- Windows SAPI ----------------------------------------------------------------------


def _decoded_script(args):
    return base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16-le")


def test_sapi_voices_pick_by_language_and_gender(monkeypatch):
    out = "Microsoft Helena Desktop|es-ES|Female\nMicrosoft Pablo Desktop|es-ES|Male\nMicrosoft Zira Desktop|en-US|Female\n"
    monkeypatch.setattr(tts, "_powershell", lambda script: subprocess.CompletedProcess([], 0, out, ""))
    assert tts.SapiEngine().voices("es") == {"guide": "Microsoft Helena Desktop", "skeptic": "Microsoft Pablo Desktop"}
    with pytest.raises(tts.EngineUnavailable) as e:
        tts.SapiEngine().voices("de")
    assert "Add voices" in e.value.fix


def test_sapi_synth_passes_text_by_file_and_quotes_safely(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        script = _decoded_script(args)
        text_file = script.split("ReadAllText('")[1].split("'")[0]
        calls.append(open(text_file, encoding="utf-8").read())
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    out = tmp_path / "it's.wav"
    tts.SapiEngine().synth("Hola, ¿qué tal? $(rm -rf /)", "Microsoft Helena Desktop", "es", 1.2, out)
    args, text = calls
    assert args[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
    script = _decoded_script(args)
    assert "SelectVoice('Microsoft Helena Desktop')" in script
    assert "$s.Rate = 2" in script
    assert "it''s.wav" in script  # single quotes escaped inside the PowerShell literal
    assert "rm -rf" not in script  # text never goes into the script
    assert text == "Hola, ¿qué tal? $(rm -rf /)"


# --- Linux espeak-ng -------------------------------------------------------------------


def test_espeak_missing_suggests_package(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda _: None)
    with pytest.raises(tts.EngineUnavailable) as e:
        tts.EspeakEngine().check()
    assert "apt install espeak-ng" in e.value.fix


def test_espeak_synth_uses_stdin_and_normalizes(monkeypatch, tmp_path):
    seen = {}

    def fake_run(args, **kw):
        seen["args"], seen["input"] = args, kw.get("input")
        tts.write_wav(tmp_path / "t.wav", b"\x10\x00" * 22050, rate=22050)  # 1 s at espeak's rate
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    tts.EspeakEngine().synth("-v hack", "es+f3", "es", 1.0, tmp_path / "t.wav")
    assert seen["args"][-1] == "--stdin" and seen["input"] == "-v hack"
    with wave.open(str(tmp_path / "t.wav")) as w:
        assert w.getframerate() == tts.SAMPLE_RATE
        assert abs(w.getnframes() - tts.SAMPLE_RATE) <= 1


def test_resample_keeps_duration():
    data = b"\x00\x01" * 22050
    out = tts.resample_pcm16(data, 22050, 24000)
    assert len(out) // 2 == 24000


# --- guided setup ----------------------------------------------------------------------


def test_setup_without_kokoro_shows_the_install_command(monkeypatch):
    monkeypatch.setattr(tts.KokoroEngine, "package_installed", lambda self: False)
    r = runner.invoke(app, ["podcast", "setup", "--lang", "es"])
    assert r.exit_code == 0, r.output
    assert "The Kokoro package is not installed." in r.output
    assert "→" in r.output and "unboringspec[podcast]" in r.output


def test_setup_downloads_only_after_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(tts.KokoroEngine, "package_installed", lambda self: True)
    monkeypatch.setenv("UNBORING_KOKORO_DIR", str(tmp_path))
    downloaded = []
    monkeypatch.setattr(tts, "download_kokoro", lambda hook=None: downloaded.append(True) or [])
    r = runner.invoke(app, ["podcast", "setup"], input="n\n")
    assert r.exit_code == 1 and not downloaded
    r = runner.invoke(app, ["podcast", "setup", "-y"])
    assert r.exit_code == 0 and downloaded
