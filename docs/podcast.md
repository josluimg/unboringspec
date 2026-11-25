# Spec podcast

Prefer to listen? Two hosts talk a spec through: a **guide** who explains it and a
**skeptic** who pushes on every risky decision and open question. The skeptic is what makes it a review and not
a summary read aloud. The audio is generated on your machine, and the review page gets a player and a
transcript whose lines link to the spec.

The podcast is **optional**. Nothing related to it is installed unless you ask for it.

- [Enable it](#enable-it)
- [Use it](#use-it)
- [Tones](#tones)
- [Voices](#voices)
- [Rendering options](#rendering-options)

## Enable it

Add the podcast skill to your agent (next to the review skill):

```bash
unboring init --ai claude --podcast
```

That is enough on macOS and Windows: the system voices work out of the box. For Linux, or for natural voices
everywhere, see [Voices](#voices).

## Use it

In your agent's chat:

```text
/unboring-podcast specs/001-my-feature es
```

Or in plain words: *"make a podcast about specs/001-my-feature, roast it, in Spanish"*. The agent writes the
script (building on the review if you already did it), and the CLI voices it:

```
unboring podcast prompt specs/001 --lang es --tone roast  →  .unboring/001/podcast.prompt.md
agent writes                                                →  .unboring/001/podcast.json (the contract)
unboring podcast render specs/001                           →  podcast.mp3, podcast.md, player in review.html
```

## Tones

Same facts, same citations, different show. Pick a preset with `--tone`, or ask your agent in your own words.

| Tone | What it sounds like |
|---|---|
| `casual` (default) | Two colleagues over coffee. |
| `formal` | A measured briefing, like an architecture review board. |
| `bro` | Close friends, heavy slang and banter: *tío*, *illo*, *en plan*, *bro*, *no cap*... |
| `roast` | A comedy roast of the spec. No mercy, all of it true. |
| `sports` | Live play-by-play, like two football commentators. Spoken a bit faster. |
| `noir` | A hard-boiled detective investigates the spec. Spoken a bit slower. |
| `eli5` | No jargon, for product, business or anyone outside engineering. |

Anything else becomes a custom tone:

```bash
unboring podcast prompt specs/001 --tone "two pirates arguing over a treasure map"
```

Whatever the tone, three rules hold: the facts stay exact and cited, every open question gets mentioned, and
nobody real is mocked (a roast targets the spec, never its authors). `unboring podcast tones` lists the presets.

## Voices

Everything runs on your machine; nothing is sent to a TTS service. There are two kinds of voices:

| | System voices | Kokoro |
|---|---|---|
| Sound | Robotic but clear | Natural ([Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)) |
| Install | Already on macOS and Windows; one package on Linux | Python package + one-time model download (~336 MB) |
| Languages | Whatever voices your OS has | en, es, fr, it, pt, hi, ja, zh |
| Speed | Instant | About 1.5 min of CPU per 5 min of audio (measured on an Intel MacBook Pro) |

### Start here

The guided setup tells you what works on your machine and the exact command for the rest:

```bash
unboring podcast setup --lang es
```

```text
Voices on macOS (x86_64), Python 3.14.3, language 'es'

  ✓ system (say)  ready · Mónica and Eddy (Español (España))
  ✗ kokoro  The Kokoro package is not installed.
      → uv tool install --python 3.12 "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"
```

Run the suggested command, then `unboring podcast setup` again: it offers to download the model, and you are
done. From then on `--engine auto` (the default) uses Kokoro, and the system voices otherwise.
`unboring podcast engines` shows the same report without downloading anything.

### System voices, by operating system

| OS | Engine | What you need |
|---|---|---|
| macOS | `say` | Nothing. More voices: System Settings › Accessibility › Spoken Content › System voice › Manage Voices |
| Windows | `sapi` 🧪 | Nothing. More languages: Settings › Time & language › Speech › Manage voices › Add voices |
| Linux | `espeak` 🧪 | `sudo apt install espeak-ng` (Fedora: `dnf`, Arch: `pacman`) |

The guide gets a female voice and the skeptic a male one when the OS has both, so they are easy to tell apart.
🧪 Windows and Linux voices are tested with mocks only so far; reports are welcome.

### Kokoro, by platform

Kokoro runs on macOS (Apple Silicon and Intel), Windows (x64 and ARM) and Linux (x64 and ARM). It brings its own
phonemizer, so there is nothing to install from the system. The one constraint is **Python 3.10 to 3.13**, which
uv solves for you:

| How you installed unboringspec | Add Kokoro |
|---|---|
| `uv tool` (recommended) | `uv tool install --python 3.12 --reinstall "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"` |
| `pipx` | `pipx inject unboringspec kokoro-onnx numpy` (on Python 3.14: `pipx install --force --python python3.12 ...`) |
| `pip` in a venv (Python ≤ 3.13) | `pip install "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"` |

`unboring podcast setup` detects which case you are in and prints the right line. The model goes to
`~/.cache/unboringspec/kokoro` (override with `UNBORING_KOKORO_DIR`); delete that folder to remove it.
On Intel Macs, uv picks ONNX Runtime 1.23, the last release built for Intel; that is the one tested.

## Rendering options

`unboring podcast render <folder>` accepts:

| Option | Meaning |
|---|---|
| `--engine` | `auto` (default: Kokoro if ready, else system), `system`, `kokoro`, `say`, `sapi`, `espeak` |
| `--voice-guide`, `--voice-skeptic` | Override a host's voice (names from `unboring podcast engines`) |
| `--speed` | 0.5 to 2.0. Default: the tone's own pace |

With ffmpeg installed you get an MP3; without it, a WAV. The transcript is written to `podcast.md`.
