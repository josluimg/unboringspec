"""Text-to-speech engines and audio assembly for the spec podcast.

Two tiers, both local (nothing is sent to a TTS service):

- system: the voices your OS already has. Zero or near-zero install, robotic but clear.
    macOS -> say, Windows -> SAPI (PowerShell), Linux -> espeak-ng.
- kokoro: Kokoro-82M through ONNX Runtime. Natural voices in 8 languages. Works on macOS
  (Apple Silicon and Intel), Windows and Linux (x64 and ARM). Needs Python 3.10-3.13, the
  `podcast` extra and a one-time model download (`unboring podcast setup`). It bundles its
  own espeak, so nothing else is needed from the system.

`--engine auto` uses Kokoro when ready, else the system voices.

Every engine writes one 24 kHz, mono, 16-bit WAV per turn; `assemble` joins them with
short pauses into an MP3 (ffmpeg) or a WAV (no extra tools needed).

Adding an engine: subclass Engine, register it in ENGINES. See CONTRIBUTING.md.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import wave
from collections.abc import Sequence
from abc import ABC, abstractmethod
from array import array
from pathlib import Path

SAMPLE_RATE = 24000
PAUSE_MS = 350  # silence between turns
Role = str  # "guide" | "skeptic"
REPO = "git+https://github.com/josluimg/unboringspec"


class EngineUnavailable(RuntimeError):
    """Raised when an engine cannot run here. `fix` is the command or step that solves it."""

    def __init__(self, message: str, fix: str | None = None):
        super().__init__(message + (f" Fix: {fix}" if fix else ""))
        self.reason = message
        self.fix = fix


def _lang(code: str) -> str:
    return code.lower().replace("_", "-").split("-")[0]


def os_name() -> str:
    return {"darwin": "macOS", "win32": "Windows"}.get(sys.platform, "Linux" if sys.platform.startswith("linux") else sys.platform)


# --- WAV helpers -----------------------------------------------------------------


def write_wav(path: Path, pcm16: bytes, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)


def resample_pcm16(data: bytes, src: int, dst: int) -> bytes:
    """Linear resampling of mono 16-bit PCM. Good enough for speech; no dependencies."""
    if src == dst:
        return data
    a = array("h")
    a.frombytes(data)
    n = len(a)
    m = int(n * dst / src)
    out = array("h", bytes(2 * m))
    ratio = src / dst
    for i in range(m):
        x = i * ratio
        j = int(x)
        s0 = a[j] if j < n else 0
        s1 = a[j + 1] if j + 1 < n else s0
        out[i] = int(s0 + (s1 - s0) * (x - j))
    return out.tobytes()


def normalize_wav(path: Path) -> None:
    """Make a WAV 24 kHz mono 16-bit in place (ffmpeg if present, pure Python otherwise)."""
    with wave.open(str(path)) as w:
        fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        frames = w.readframes(w.getnframes())
    if fmt == (1, 2, SAMPLE_RATE):
        return
    if shutil.which("ffmpeg"):
        tmp = path.with_suffix(".norm.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-sample_fmt", "s16", str(tmp)],
            check=True,
        )
        tmp.replace(path)
        return
    if fmt[:2] != (1, 2):
        raise RuntimeError(f"{path.name} is not mono 16-bit; install ffmpeg to convert it.")
    write_wav(path, resample_pcm16(frames, fmt[2], SAMPLE_RATE))


# --- engine contract -------------------------------------------------------------

Terms = Sequence[tuple[str, str]]  # (word, BCP 47 language), e.g. ("Snowflake", "en")


def split_by_language(text: str, terms) -> list[tuple[str, str | None]]:
    """Cut a turn into pieces: (piece, language) for the listed terms, (piece, None) for the rest.

    Terms match whole words, case-insensitively, longest first, so "Control-M" wins over "Control".
    """
    terms = [(w.strip(), lang) for w, lang in terms if w.strip()]
    if not terms:
        return [(text, None)] if text else []
    by_word = {w.lower(): lang for w, lang in terms}
    words = sorted(by_word, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.IGNORECASE)
    pieces: list[tuple[str, str | None]] = []
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            pieces.append((text[pos:m.start()], None))
        pieces.append((m.group(0), by_word[m.group(0).lower()]))
        pos = m.end()
    if pos < len(text):
        pieces.append((text[pos:], None))
    return pieces


class Engine(ABC):
    name: str = ""
    tier: str = "system"  # "system" or "neural"
    description: str = ""

    @abstractmethod
    def check(self) -> None:
        """Raise EngineUnavailable (with a fix) if the engine cannot run here."""

    @abstractmethod
    def voices(self, lang: str) -> dict[Role, str]:
        """Default voices for the guide and the skeptic in this language."""

    @abstractmethod
    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path, terms: Terms = ()) -> None:
        """Write one turn as a 24 kHz mono 16-bit WAV. `terms` are (word, language) pairs to say in
        that language (#57); engines that cannot switch language mid-sentence ignore them."""


def _pick_two(candidates: list[tuple[str, str]]) -> dict[Role, str]:
    """candidates: (voice, gender) with gender in {"female", "male", ""}. Guide prefers a female
    voice and the skeptic a male one, so the two hosts are easy to tell apart."""
    female = [v for v, g in candidates if g == "female"]
    male = [v for v, g in candidates if g == "male"]
    names = [v for v, _ in candidates]
    guide = (female or names)[0]
    skeptic = next((v for v in male if v != guide), None) or next((v for v in names if v != guide), guide)
    return {"guide": guide, "skeptic": skeptic}


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


def kokoro_install_hint() -> str:
    """The exact command to add Kokoro, depending on how unboringspec was installed here."""
    prefix = Path(sys.prefix).as_posix().lower()
    spec = f'"unboringspec[podcast] @ {REPO}"'
    if "/uv/tools/" in prefix:
        return f"uv tool install --python 3.12 --reinstall {spec}"
    if "/pipx/venvs/" in prefix:
        if sys.version_info >= (3, 14):
            return f"pipx install --force --python python3.12 {spec}"
        return "pipx inject unboringspec kokoro-onnx numpy"
    if sys.version_info >= (3, 14):
        return f"uv tool install --python 3.12 {spec}  (Kokoro needs Python 3.10-3.13; uv fetches it for you)"
    return f"{Path(sys.executable).name} -m pip install {spec}"


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
    tier = "neural"
    description = "Kokoro-82M via ONNX Runtime: natural voices, 8 languages, runs on CPU"

    def __init__(self) -> None:
        self._model = None

    def _paths(self) -> tuple[Path, Path]:
        d = kokoro_dir()
        return d / KOKORO_FILES["model"][0], d / KOKORO_FILES["voices"][0]

    def package_installed(self) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return True

    def model_installed(self) -> bool:
        return all(p.exists() for p in self._paths())

    def check(self) -> None:
        if not self.package_installed():
            raise EngineUnavailable("The Kokoro package is not installed.", kokoro_install_hint())
        if not self.model_installed():
            size = sum(s for _, s in KOKORO_FILES.values())
            raise EngineUnavailable(f"The Kokoro model (~{size} MB) is not downloaded yet.", "unboring podcast setup")

    def voices(self, lang: str) -> dict[Role, str]:
        return KOKORO_VOICES.get(_lang(lang), KOKORO_VOICES["en"])

    def _phonemes(self, piece: str, lang: str) -> str:
        # Hyphens and underscores in names ("Control-M") are read as spaces, not as "minus".
        return self._model.tokenizer.phonemize(re.sub(r"[-_]", " ", piece), lang).strip()

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path, terms: Terms = ()) -> None:
        import numpy as np
        from kokoro_onnx import Kokoro

        if self._model is None:
            model, voices = self._paths()
            try:
                self._model = Kokoro(str(model), str(voices))
            except Exception as e:  # onnxruntime raises its own exception types
                raise EngineUnavailable(
                    f"Kokoro could not load {model.name}: {e}.",
                    f"delete {kokoro_dir()} and run `unboring podcast setup` again, or use --engine system",
                ) from e
        base = KOKORO_LANGS.get(_lang(lang), "en-us")
        pieces = split_by_language(text, terms)
        if any(piece_lang for _, piece_lang in pieces):
            # Each piece phonemized with its own language's rules, so "Snowflake" in a Spanish turn
            # is said /snˈoʊfleɪk/ and not /snowflˈake/; Kokoro then speaks the phonemes.
            phonemes = " ".join(
                p for p in (
                    self._phonemes(piece, KOKORO_LANGS.get(_lang(piece_lang), base) if piece_lang else base)
                    for piece, piece_lang in pieces
                ) if p
            )
            samples, rate = self._model.create(phonemes, voice=voice, speed=speed, lang=base, is_phonemes=True)
        else:
            samples, rate = self._model.create(text, voice=voice, speed=speed, lang=base)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        write_wav(out, pcm, rate)
        normalize_wav(out)


# --- macOS: say ------------------------------------------------------------------

SAY_LINE = re.compile(r"^(.+?)\s+([a-z]{2,3}_[A-Z0-9]{2,3})\s+#")
# say does not report gender; these are well-known macOS voices, in order of preference.
SAY_GENDER = {
    "Mónica": "female", "Paulina": "female", "Flo (Español (España))": "female", "Flo (Español (México))": "female",
    "Samantha": "female", "Amélie": "female", "Alice": "female", "Luciana": "female", "Karen": "female",
    "Eddy (Español (España))": "male", "Eddy (Español (México))": "male", "Jorge": "male", "Daniel": "male",
    "Fred": "male", "Thomas": "male", "Luca": "male", "Grandpa (Español (España))": "male",
}


class SayEngine(Engine):
    name = "say"
    description = "macOS system voices"

    def check(self) -> None:
        if sys.platform != "darwin" or not shutil.which("say"):
            raise EngineUnavailable("The 'say' command only exists on macOS.")

    def _installed(self) -> list[tuple[str, str]]:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
        return [(m.group(1).strip(), m.group(2)) for line in out.splitlines() if (m := SAY_LINE.match(line))]

    def voices(self, lang: str) -> dict[Role, str]:
        lang = _lang(lang)
        installed = [name for name, loc in self._installed() if loc.lower().startswith(lang)]
        if not installed:
            raise EngineUnavailable(
                f"macOS has no '{lang}' voice installed.",
                "System Settings > Accessibility > Spoken Content > System voice > Manage Voices",
            )
        # Preferred voices first, so a natural pair wins over novelty voices like Grandma.
        order = list(SAY_GENDER)
        ranked = sorted(installed, key=lambda v: order.index(v) if v in order else len(order))
        return _pick_two([(v, SAY_GENDER.get(v, "")) for v in ranked])

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path, terms: Terms = ()) -> None:
        subprocess.run(
            ["say", "-v", voice, "-r", str(int(180 * speed)), "-o", str(out), "--file-format=WAVE",
             f"--data-format=LEI16@{SAMPLE_RATE}", text],
            check=True,
            capture_output=True,
        )


# --- Windows: SAPI through PowerShell ----------------------------------------------


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell(script: str) -> subprocess.CompletedProcess:
    """Run a script with -EncodedCommand: no quoting issues and no script file to trust."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        check=True,
    )


class SapiEngine(Engine):
    name = "sapi"
    description = "Windows system voices (SAPI)"

    def check(self) -> None:
        if sys.platform != "win32" or not shutil.which("powershell"):
            raise EngineUnavailable("SAPI voices only exist on Windows.")

    def _installed(self) -> list[tuple[str, str, str]]:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { "
            "$v = $_.VoiceInfo; '{0}|{1}|{2}' -f $v.Name, $v.Culture.Name, $v.Gender }"
        )
        out = _powershell(script).stdout
        rows = []
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2].lower()))
        return rows

    def voices(self, lang: str) -> dict[Role, str]:
        lang = _lang(lang)
        installed = [(n, g) for n, culture, g in self._installed() if culture.lower().startswith(lang)]
        if not installed:
            raise EngineUnavailable(
                f"Windows has no '{lang}' voice installed.",
                "Settings > Time & language > Speech > Manage voices > Add voices",
            )
        return _pick_two(installed)

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path, terms: Terms = ()) -> None:
        rate = max(-10, min(10, round((speed - 1.0) * 10)))
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(text)
            text_file = f.name
        try:
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SelectVoice({_ps_literal(voice)}); $s.Rate = {rate}; "
                "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo("
                f"{SAMPLE_RATE}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
                "[System.Speech.AudioFormat.AudioChannel]::Mono); "
                f"$s.SetOutputToWaveFile({_ps_literal(str(out))}, $fmt); "
                f"$s.Speak([IO.File]::ReadAllText({_ps_literal(text_file)}, [Text.Encoding]::UTF8)); "
                "$s.Dispose()"
            )
            _powershell(script)
        finally:
            os.unlink(text_file)


# --- Linux: espeak-ng ------------------------------------------------------------


class EspeakEngine(Engine):
    name = "espeak"
    description = "espeak-ng system voices (Linux)"

    def _binary(self) -> str | None:
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def check(self) -> None:
        if not self._binary():
            raise EngineUnavailable(
                "espeak-ng is not installed.",
                "sudo apt install espeak-ng  (Fedora: sudo dnf install espeak-ng, Arch: sudo pacman -S espeak-ng)",
            )

    def voices(self, lang: str) -> dict[Role, str]:
        lang = _lang(lang)
        return {"guide": f"{lang}+f3", "skeptic": f"{lang}+m3"}

    def synth(self, text: str, voice: str, lang: str, speed: float, out: Path, terms: Terms = ()) -> None:
        subprocess.run(
            [self._binary(), "-v", voice, "-s", str(int(165 * speed)), "-w", str(out), "--stdin"],
            input=text,
            text=True,
            check=True,
            capture_output=True,
        )
        normalize_wav(out)  # espeak writes 22.05 kHz


# --- registry and selection ------------------------------------------------------

ENGINES: dict[str, type[Engine]] = {"kokoro": KokoroEngine, "say": SayEngine, "sapi": SapiEngine, "espeak": EspeakEngine}
SYSTEM_ENGINE = {"darwin": "say", "win32": "sapi"}


def system_engine_name() -> str:
    return SYSTEM_ENGINE.get(sys.platform, "espeak")


def pick_engine(name: str = "auto") -> Engine:
    """'auto': Kokoro when ready, else this OS's system voices. 'system': the OS voices."""
    if name == "system":
        name = system_engine_name()
    if name != "auto":
        if name not in ENGINES:
            raise EngineUnavailable(f"Unknown engine '{name}'. Available: auto, system, {', '.join(ENGINES)}.")
        engine = ENGINES[name]()
        engine.check()
        return engine
    reasons = []
    for candidate in ("kokoro", system_engine_name()):
        engine = ENGINES[candidate]()
        try:
            engine.check()
            return engine
        except EngineUnavailable as e:
            reasons.append(f"- {candidate}: {e}")
    raise EngineUnavailable("No voice engine is ready.\n" + "\n".join(reasons))


# --- assembly --------------------------------------------------------------------


def _silence(path: Path, ms: int) -> Path:
    write_wav(path, b"\x00\x00" * int(SAMPLE_RATE * ms / 1000))
    return path


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


# Constant bitrate, not VBR: time maps exactly to bytes, so every browser can seek the episode over
# HTTP ranges. With VBR, WebKit estimates the offset and can stall after a seek (#59). 64 kb/s mono
# is plenty for speech at 24 kHz.
MP3_ENCODING = ("-c:a", "libmp3lame", "-b:a", "64k")


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
             "-ar", str(SAMPLE_RATE), "-ac", "1", *MP3_ENCODING, str(out)],
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
