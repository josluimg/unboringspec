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
- [A cast of voices](#a-cast-of-voices)
- [Words in another language](#words-in-another-language)
- [Pace and the player](#pace-and-the-player)
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

The episode stays on the review page across later renders. If the spec changes after it was recorded, the page
says the episode is about an earlier version (and how many changes since), drops its links to spec lines, and
`unboring render` prints the same notice: record a new one with `/unboring-podcast`.

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
| Speed | Instant | About three times faster than real time on a laptop CPU (measured on an Intel MacBook Pro) |

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
| Windows | `windows`, `sapi` | Nothing. `windows` reaches the modern voices too (Spanish: Pablo, Laura, Helena); `sapi`, the classic ones only, is the fallback. More languages: Settings › Time & language › Speech › Manage voices › Add voices |
| Linux | `espeak` 🧪 | `sudo apt install espeak-ng` (Fedora: `dnf`, Arch: `pacman`) |

The guide gets a female voice and the skeptic a male one when the OS has both, so they are easy to tell apart.
When the language has a single voice (with `sapi`, Windows often shows only *Microsoft Helena Desktop* in Spanish), the skeptic
uses that voice three semitones lower. With ffmpeg the shift keeps the voice natural; without it, Windows lowers
the pitch through SSML and espeak-ng uses its own pitch setting. For two real voices, add Kokoro.
🧪 Linux voices are tested with mocks only so far; reports are welcome.

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

## A cast of voices

Kokoro has few voices in some languages (three in Spanish), so episodes would always sound the same. Each
recording with Kokoro therefore picks its hosts at random from a **cast**. The guide comes from one list and
the skeptic from another, so the names the script gives them still fit, and the two are easy to tell apart.
The Spanish cast:

| Guide | Skeptic |
|---|---|
| `ef_dora` | `em_alex` |
| `ef_dora*0.5+af_bella*0.5` | `em_santa` |
| `ef_dora*0.6+em_alex*0.4` | `em_alex*0.6+em_santa*0.4` |
| | `em_alex@-2` |

A voice can be a blend of Kokoro voices with weights (`a*0.6+b*0.4`), and `@-2` lowers its pitch two semitones
without changing its speed (needs ffmpeg; without it, those voices leave the cast). The voices used are printed
and saved in `podcast.meta.json`. To keep a pair, pin it:

```bash
unboring podcast render specs/001 --voice-guide "ef_dora*0.6+em_alex*0.4" --voice-skeptic "em_alex@-2"
```

Other languages use their default pair until someone has listened to a cast for them.

## Words in another language

Teams say a lot of things in English whatever language they speak: product names (*Snowflake*, *PostgreSQL*)
and jargon (*endpoint*, *deadline*, *backoffice*). The script keeps that jargon as the team says it, and lists
those words with their language in `terms`. With Kokoro, each one is pronounced with its own language's rules
inside the sentence, so a Spanish host says *Snowflake* the English way instead of reading it letter by letter
in Spanish. The transcript is unchanged.

Words that are not jargon go in the episode's language: a Spanish episode talks about *la especificación*,
not *la spec*.

System voices cannot switch language in the middle of a sentence, so they read those words with the episode's
language rules; `podcast render` says so when it happens.

## Pace and the player

Natural voices sound slow at their nominal speed, so episodes are recorded at **1.2** by default. Each tone
keeps its own pace on top of that (sports commentary a little faster, the noir detective a little slower), and
`--speed` replaces the result for one recording.

Episodes are split into **chapters**: the hook, what it is, the key decisions, what you must decide, and the
wrap-up. The script marks the first turn of each; the recording measures where each one starts. On the review page
they are buttons under the player (the current one is highlighted while you listen) and headings in the
transcript, and the MP3 carries them as ID3 chapters, so podcast apps show them too. The most useful one is
*what you must decide*: one click and you are there.

On the review page the player shows the speed at all times: **1×, 1.25×, 1.5×, 2×**, on top of the recorded
pace. The choice is remembered in that browser. Without JavaScript, the browser's own player shows instead.

## Rendering options

`unboring podcast render <folder>` accepts:

| Option | Meaning |
|---|---|
| `--engine` | `auto` (default: Kokoro if ready, else system), `system`, `kokoro`, `say`, `windows`, `sapi`, `espeak` |
| `--voice-guide`, `--voice-skeptic` | Pin a host's voice: a name from `unboring podcast engines` or, with Kokoro, a blend and pitch (see [A cast of voices](#a-cast-of-voices)). Default: a pair picked at random from the cast |
| `--speed` | 0.5 to 2.0. Default: 1.2 times the tone's own pace (see [Pace and the player](#pace-and-the-player)) |

With ffmpeg installed you get an MP3; without it, a WAV. The transcript is written to `podcast.md`.
