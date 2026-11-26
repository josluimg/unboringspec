# FAQ

- [Podcast](#podcast)
  - [How is the voice generated?](#how-is-the-voice-generated)
  - [What is Kokoro, and are there alternatives?](#what-is-kokoro-and-are-there-alternatives)
  - [Does the podcast cost money or consume tokens?](#does-the-podcast-cost-money-or-consume-tokens)
  - [Privacy: does anything leave my machine?](#privacy-does-anything-leave-my-machine)
- [Requirements](#requirements)
  - [What do I need to install?](#what-do-i-need-to-install)
  - [What do I need for the podcast?](#what-do-i-need-for-the-podcast)
  - [My project is pure Node / TypeScript. Do I need Python?](#my-project-is-pure-node--typescript-do-i-need-python)
- [The review](#the-review)
  - [Does the review cost tokens?](#does-the-review-cost-tokens)
  - [Will unboringspec change my spec?](#will-unboringspec-change-my-spec)
  - [The buttons on the page do nothing. Why?](#the-buttons-on-the-page-do-nothing-why)
  - [Can I use it without a coding agent?](#can-i-use-it-without-a-coding-agent)
  - [Can the page use my company's colours and fonts?](#can-the-page-use-my-companys-colours-and-fonts)

## Podcast

### How is the voice generated?

In two steps that never mix:

1. **The script** is written by your coding agent (Claude Code, Copilot, Codex…), the same way it writes the
   review: it reads the spec and the review's analysis, and writes a conversation between a guide and a skeptic
   in the tone you asked for.
2. **The voice** is generated **on your machine** by a text-to-speech (TTS) engine, one turn at a time, and
   the turns are joined into an MP3 (or a WAV without ffmpeg).

There are two kinds of engine, and `--engine auto` picks the best one available:

| | System voices | Kokoro |
|---|---|---|
| What it is | The voices your operating system already has: `say` on macOS, SAPI on Windows, espeak-ng on Linux | An open-weight neural TTS model |
| Sound | Robotic but clear | Natural |
| Install | Nothing on macOS and Windows; one package on Linux | A Python package plus a one-time model download (~336 MB) |
| Languages | Whatever voices your OS has installed | English, Spanish, French, Italian, Portuguese, Hindi, Japanese, Chinese |

`unboring podcast setup` tells you what works on your machine and the exact command for the rest. Details in the
[podcast guide](podcast.md#voices).

### What is Kokoro, and are there alternatives?

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) is a small text-to-speech model (82 million parameters)
published with open weights under the **Apache 2.0** licence. Being small, it runs on an ordinary laptop CPU, with
no GPU, at about three times faster than real time on an Intel MacBook Pro. unboringspec runs it through
[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT) and ONNX Runtime, which bundles its own
phonemizer, so nothing else is needed from the system.

Each language comes with its own voices; the guide gets a female voice and the skeptic a male one when both exist
(in Spanish, `ef_dora` and `em_alex`).

Alternatives:

- **System voices**: built in, instant, no download. Fine for a quick listen; less pleasant for a long one.
- **Planned engines**: [Piper](https://github.com/OHF-Voice/piper1-gpl) (fast and light, many languages;
  [#19](https://github.com/josluimg/unboringspec/issues/19)) and
  [Chatterbox](https://github.com/resemble-ai/chatterbox) (more expressive, heavier;
  [#20](https://github.com/josluimg/unboringspec/issues/20)).
- **Cloud TTS services** (ElevenLabs, OpenAI, Azure…) are deliberately not supported: the audio is generated
  locally, so a spec never has to be sent to a voice service.

Voice engines are pluggable; adding one is described in [CONTRIBUTING.md](../CONTRIBUTING.md#add-a-tts-engine).

### Does the podcast cost money or consume tokens?

**Only the script does.** Writing it is a normal request to your coding agent, so it uses tokens from your agent's
plan or API key, like any other prompt:

- **Input**: the spec's documents (line-numbered), the review's analysis if you made one, and the instructions.
- **Output**: the script, a conversation as long as a short article.

To give an idea, on the [example spec](../examples/speckit/specs/001-photo-albums/) (four documents, 6.7 KB) the
podcast prompt is about 21 KB and the script about 10 KB, roughly 5,000 to 6,000 tokens in and 2,500 out. It grows
with the size of your spec.

**The voice costs nothing**: no tokens, no subscription, no per-character fee. Once the Kokoro model is
downloaded, generating audio works offline.

### Privacy: does anything leave my machine?

- **The spec** goes to the model your coding agent already uses, exactly as when you ask it anything else
  about your code. unboringspec adds no other service.
- **The voices** are generated locally.
- **The review page** is a local file. Diagrams are drawn by Mermaid, which the page loads from a CDN the first
  time you open one; the library is downloaded, your diagrams are not uploaded.
- **Downloads** happen only when you ask: the Kokoro model with `unboring podcast setup`.

## Requirements

### What do I need to install?

| For | You need |
|---|---|
| The CLI | Python 3.10 or newer, installed with [uv](https://docs.astral.sh/uv/) (recommended: it fetches a suitable Python for you), pipx or pip. Works on macOS, Windows and Linux |
| The analysis | A coding agent (Claude Code tested end to end; Copilot, Codex, Cursor and Gemini CLI follow their documented formats), or an API key for [CI](setup.md#in-ci) |
| The review page | A web browser with JavaScript; an internet connection to draw diagrams (without it, their source is shown) |
| Optional | git, to compare with any commit (`--since`); ffmpeg, to get MP3 instead of WAV |

Nothing is added to your repository except `.unboring/` (git-ignored) and the skills in your agent's folder.

### What do I need for the podcast?

The podcast is optional: it needs nothing until you add it with `unboring init --podcast`.

| Voices | Requirements |
|---|---|
| System voices on macOS or Windows | Nothing more |
| System voices on Linux | `sudo apt install espeak-ng` (or your distribution's equivalent) |
| Kokoro | Python 3.10 to 3.13 for the tool (uv provides it even if your system has 3.14), the `podcast` extra, ~336 MB of disk for the model, any recent CPU. On Intel Macs it uses ONNX Runtime 1.23, the last release built for Intel |

`unboring podcast setup` checks all of this and prints the command for whatever is missing.

### Windows blocks `unboring.exe`. What can I do?

Installing the CLI creates a small launcher, `unboring.exe`, in the environment's `Scripts\` folder. Antivirus,
SmartScreen or company policies (AppLocker, WDAC) often block executables in user folders, while Python itself is
allowed. Run the same CLI through Python instead:

```bash
python -m unboringspec render specs/001-x
```

Every command and option is the same. It needs the package installed in that Python, for example with
`pip install git+https://github.com/josluimg/unboringspec` inside your virtual environment: `uv tool` and pipx keep
it in an isolated environment the plain `python` does not see. The agent skills fall back to `python -m unboringspec`
on their own when `unboring` does not start.

### My project is pure Node / TypeScript. Do I need Python?

Today you need `uv`, a single binary that brings its own Python; nothing Python lands in your repository or your
`package.json`. You can even run the tool without installing it:

```bash
uvx --from git+https://github.com/josluimg/unboringspec unboring review specs/001-x --offline
```

Teams on spec-kit already have uv, since spec-kit's own CLI is installed with it. A Python-free distribution through
npm is planned: standalone binaries ([#34](https://github.com/josluimg/unboringspec/issues/34)) and Kokoro voices as
a separate optional package ([#35](https://github.com/josluimg/unboringspec/issues/35)).

## The review

### Does the review cost tokens?

The analysis does, in the same way as the podcast script: your agent reads the spec and writes the analysis. On the
example spec, the prompt is about 14 KB and the analysis about 9 KB. Everything else (parsing the spec, validating
citations, comparing versions, rendering the page and the diagrams built from the spec) is done by the CLI, with no
model involved.

### Will unboringspec change my spec?

No. **unboringspec reviews; your framework changes the spec.** When you hand a review back, `unboring feedback` tells
your agent which of your framework's commands to run (`/speckit-clarify`, `/speckit-plan`, `/speckit-tasks` for
spec-kit; `/opsx:update` for OpenSpec), and the skill forbids editing spec files directly when those commands exist.
See [Bringing your review back](setup.md#bringing-your-review-back).

### The buttons on the page do nothing. Why?

The page needs JavaScript for approving and questioning decisions, answering, exporting, the source viewer and the
diagrams. Some viewers, like static HTML previews inside apps, do not run it; the page then says so at the top.
Open `review.html` in a web browser, or render it with `--open`.

### Can I use it without a coding agent?

Yes, two ways:

- **In CI**, with an API key for any model [LiteLLM](https://docs.litellm.ai/docs/providers) supports:
  `unboring review specs/001-x --model …`. See [In CI](setup.md#in-ci).
- **To look around**, with no model at all: `unboring review specs/001-x --offline` shows what the framework's
  structure gives (stories, requirements, tasks, open markers), without the analysis. See
  [Quick try, no LLM](setup.md#quick-try-no-llm).

### Can the page use my company's colours and fonts?

Yes. Put an `unboring.css` at the root of your project, and every review uses it with no extra option; commit it so
the whole team gets the same look. `unboring theme init` writes one with every setting commented out, so you only
uncomment what you want to change: colours for light and dark, fonts, corner radius, or any other CSS. Diagrams
follow the same colours. See [Customise the look](setup.md#customise-the-look) for the list of tokens and the rules.

