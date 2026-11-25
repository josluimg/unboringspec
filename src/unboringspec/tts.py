"""Text-to-speech engines and audio assembly for the spec podcast.

Engines are pluggable. Each one writes a 24 kHz, mono, 16-bit WAV per turn; `assemble`
joins them with short pauses into an MP3 (ffmpeg) or a WAV (no extra tools needed).

- kokoro: Kokoro-82M through ONNX Runtime. Good quality, local, many languages
  (English, Spanish, French, Italian, Portuguese, Hindi, Japanese, Chinese). Needs the
  `podcast` extra and `unboring podcast setup` once to download the model.
- say: the voices built into macOS. Zero install, lower quality. Handy for a quick try.

Adding an engine: subclass Engine, register it in ENGINES. See CONTRIBUTING.md.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import wave
from abc import ABC, abstractmethod
from pathlib import Path

SAMPLE_RATE = 24000
PAUSE_MS = 350  # silence between turns
Role = str  # "guide" | "skeptic"


class EngineUnavailable(RuntimeError):
    pass


def _lang(code: str) -> str:
    return code.lower().replace("_", "-").split("-")[0]


def write_wav(path: Path, pcm16: bytes, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)


class Engine(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def check(self) -> None:
        """Raise EngineUnavailable with an actionable message if the engine cannot run here."""

    @abstractmethod
    def voices(self, lang: str) -> dict[Role, str]:
        """Default voices for the guide and the skeptic in this language."""

    @abstractmethod
    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path) -> None:
        """Write one turn as a 24 kHz mono 16-bit WAV."""


# --- Kokoro (ONNX) ---------------------------------------------------------------

KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
# Only the full-precision model: the int8 build uses ConvInteger, which ONNX Runtime's CPU
# provider does not implement on every platform (it fails on Intel macOS, for example).
KOKORO_FILES = {
    "model": ("kokoro-v1.0.onnx", 310),
    "voices": ("voices-v1.0.bin", 26),
}
# kokoro-onnx language codes (espeak) and voices: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
KOKORO_LANGS = {"en": "en-us", "es": "es", "fr": "fr-fr", "it": "it", "pt": "pt-br", "hi": "hi", "ja": "ja", "zh": "cmn"}
KOKORO_VOICES = {
    "en": {"guide": "af_heart", "skeptic": "am_michael"},
    "es": {"guide": "ef_dora", "skeptic": "em_alex"},
    "fr": {"guide": "ff_siwis", "skeptic": "ff_siwis"},
    "it": {"guide": "if_sara", "skeptic": "im_nicola"},
    "pt": {"guide": "pf_dora", "skeptic": "pm_alex"},
    "hi": {"guide": "hf_alpha", "skeptic": "hm_omega"},
    "ja": {"guide": "jf_alpha", "skeptic": "jm_kumo"},
    "zh": {"guide": "zf_xiaobei", "skeptic": "zm_yunjian"},
}


def kokoro_dir() -> Path:
    return Path(os.environ.get("UNBORING_KOKORO_DIR", Path.home() / ".cache" / "unboringspec" / "kokoro"))


def download_kokoro(progress=None) -> list[Path]:
    """Download the Kokoro model and voices into kokoro_dir(). Returns the files."""
    target = kokoro_dir()
    target.mkdir(parents=True, exist_ok=True)
    out = []
    for key in ("model", "voices"):
        name, _ = KOKORO_FILES[key]
        dest = target / name
        if not dest.exists():
            part = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(f"{KOKORO_RELEASE}/{name}", part, reporthook=progress)
            part.rename(dest)
        out.append(dest)
    return out


class KokoroEngine(Engine):
    name = "kokoro"
    description = "Kokoro-82M via ONNX Runtime: local, natural voices, many languages"

    def __init__(self) -> None:
        self._model = None

    def _paths(self) -> tuple[Path, Path]:
        d = kokoro_dir()
        return d / KOKORO_FILES["model"][0], d / KOKORO_FILES["voices"][0]

    def check(self) -> None:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            hint = (
                "Kokoro needs Python 3.10 to 3.13. With uv: "
                'uv tool install --python 3.12 "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"'
                if sys.version_info >= (3, 14)
                else 'pip install "unboringspec[podcast]"'
            )
            raise EngineUnavailable(f"kokoro-onnx is not installed. {hint}")
        model, voices = self._paths()
        if not (model.exists() and voices.exists()):
            raise EngineUnavailable(f"Kokoro model files are missing in {kokoro_dir()}. Run: unboring podcast setup")

    def voices(self, lang: str) -> dict[Role, str]:
        return KOKORO_VOICES.get(_lang(lang), KOKORO_VOICES["en"])

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path) -> None:
        import numpy as np
        from kokoro_onnx import Kokoro

        if self._model is None:
            model, voices = self._paths()
            try:
                self._model = Kokoro(str(model), str(voices))
            except Exception as e:  # onnxruntime raises its own exception types
                raise EngineUnavailable(
                    f"Kokoro could not load {model.name}: {e}. "
                    f"Delete {kokoro_dir()} and run `unboring podcast setup` again, or use --engine say."
                ) from e
        samples, rate = self._model.create(text, voice=voice, speed=speed, lang=KOKORO_LANGS.get(_lang(lang), "en-us"))
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        write_wav(out, pcm, rate)


# --- macOS say -------------------------------------------------------------------

SAY_LINE = re.compile(r"^(.+?)\s+([a-z]{2,3}_[A-Z0-9]{2,3})\s+#")
SAY_PREFERRED = {
    "guide": ["Mónica", "Paulina", "Flo (Español (España))", "Samantha", "Amélie", "Alice", "Luciana"],
    "skeptic": ["Eddy (Español (España))", "Jorge", "Eddy (Español (México))", "Daniel", "Fred", "Thomas", "Luca"],
}


class SayEngine(Engine):
    name = "say"
    description = "Voices built into macOS: zero install, robotic but clear"

    def check(self) -> None:
        if sys.platform != "darwin" or not shutil.which("say"):
            raise EngineUnavailable("The 'say' engine only exists on macOS.")

    def _installed(self) -> list[tuple[str, str]]:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
        return [(m.group(1).strip(), m.group(2)) for line in out.splitlines() if (m := SAY_LINE.match(line))]

    def voices(self, lang: str) -> dict[Role, str]:
        lang = _lang(lang)
        installed = [name for name, loc in self._installed() if loc.lower().startswith(lang)]
        if not installed:
            raise EngineUnavailable(f"macOS has no '{lang}' voice installed (System Settings > Accessibility > Spoken Content).")
        chosen: dict[Role, str] = {}
        for role in ("guide", "skeptic"):
            pick = next((v for v in SAY_PREFERRED[role] if v in installed and v not in chosen.values()), None)
            pick = pick or next((v for v in installed if v not in chosen.values()), installed[0])
            chosen[role] = pick
        return chosen

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path) -> None:
        rate = str(int(180 * speed))
        subprocess.run(
            ["say", "-v", voice, "-r", rate, "-o", str(out), "--file-format=WAVE", f"--data-format=LEI16@{SAMPLE_RATE}", text],
            check=True,
            capture_output=True,
        )


ENGINES: dict[str, type[Engine]] = {"kokoro": KokoroEngine, "say": SayEngine}


def pick_engine(name: str = "auto") -> Engine:
    """'auto' prefers Kokoro and falls back to macOS say."""
    if name != "auto":
        if name not in ENGINES:
            raise EngineUnavailable(f"Unknown engine '{name}'. Available: {', '.join(ENGINES)}")
        engine = ENGINES[name]()
        engine.check()
        return engine
    reasons = []
    for cls in ENGINES.values():
        engine = cls()
        try:
            engine.check()
            return engine
        except EngineUnavailable as e:
            reasons.append(f"{cls.name}: {e}")
    raise EngineUnavailable("No TTS engine available.\n" + "\n".join(reasons))


# --- assembly --------------------------------------------------------------------


def _silence(path: Path, ms: int) -> Path:
    write_wav(path, b"\x00\x00" * int(SAMPLE_RATE * ms / 1000))
    return path


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def assemble(parts: list[Path], out_stem: Path, pause_ms: int = PAUSE_MS) -> Path:
    """Join turn WAVs with pauses. MP3 when ffmpeg is available, WAV otherwise."""
    work = parts[0].parent
    gap = _silence(work / "_pause.wav", pause_ms)
    sequence: list[Path] = []
    for i, p in enumerate(parts):
        if i:
            sequence.append(gap)
        sequence.append(p)

    if shutil.which("ffmpeg"):
        listing = work / "_concat.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in sequence), encoding="utf-8")
        out = out_stem.with_suffix(".mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "libmp3lame", "-q:a", "4", str(out)],
            check=True,
        )
        return out

    out = out_stem.with_suffix(".wav")
    with wave.open(str(out), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(SAMPLE_RATE)
        for p in sequence:
            with wave.open(str(p)) as src:
                if (src.getnchannels(), src.getsampwidth(), src.getframerate()) != (1, 2, SAMPLE_RATE):
                    raise RuntimeError(f"{p} is not 24 kHz mono 16-bit; install ffmpeg to mix other formats.")
                dst.writeframes(src.readframes(src.getnframes()))
    return out
