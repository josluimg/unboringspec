# unboringspec

**Specs your brain actually wants to review.**

Spec-Driven Development (SDD) moved the bottleneck. Agents now write the code, and people spend their day
reading long specs, plans, research notes and task lists. It is exhausting, and the few decisions that really
need a human get lost in the volume.

unboringspec turns a spec folder into a **review built around your attention**: what needs your judgment comes
first, everything else stays one click away, and every claim links back to the line it came from. It works
with the SDD framework you use and the coding agent you already have, with no extra API key.

## What you get

| | |
|---|---|
| ⏱️ **30-second summary** | What is being built, in five bullets. |
| 🧭 **Needs your judgment** | Only what is blocked on a human: `[NEEDS CLARIFICATION]` markers, unresolved trade-offs, gaps a careful reviewer would raise. |
| 🃏 **Decision cards** | Each decision with its rationale, the alternatives it beat and its risk. Approve it or question it. |
| 🗺️ **Visual overview** | The task graph and the data model drawn from the spec, plus the user journey and a key sequence drawn by your agent. Collapsed until you open them. |
| 📂 **Progressive disclosure** | Routine decisions, stories, tasks and requirements stay collapsed until you want them. |
| 🔗 **Traceability** | Every claim links to its `file:line`; the source opens beside the summary. Invented citations are dropped. |
| 🔁 **Feedback loop** | Export your verdicts as `review.md` and hand it back to your agent to update the spec. |
| 🎧 **Spec podcast** *(optional)* | A guide and a skeptic talk the spec through in ~5 minutes, voiced locally. Formal, casual, roast, sports commentary... |

## Quick start

**In your IDE with a coding agent** (recommended):

```bash
uv tool install git+https://github.com/josluimg/unboringspec
cd your-project
unboring init --ai claude          # or copilot, codex, cursor, gemini
```

Then ask your agent: `/unboring-review specs/001-my-feature`. Open `.unboring/001-my-feature/review.html`.

**Just looking?** Try it on the bundled example, no LLM involved:

```bash
git clone https://github.com/josluimg/unboringspec && cd unboringspec
python -m venv .venv && source .venv/bin/activate && pip install -e .
unboring review examples/speckit/specs/001-photo-albums --offline --open
unboring review examples/openspec/openspec/changes/add-invite-link-revocation --offline --open   # OpenSpec
```

📘 **[Setup and usage guide](docs/setup.md)**: install options, every agent, CI with an API key, all commands.
🎧 **[Podcast guide](docs/podcast.md)**: enabling it, tones, and voices on macOS, Windows and Linux.

## What it supports

**SDD frameworks** through adapters. Each one states the framework version it was tested with, and warns if a
document no longer parses (a sign the template changed) instead of showing an empty review.

| Framework | Status |
|---|---|
| [spec-kit](https://github.com/github/spec-kit) | ✅ tested with v1.4.4 templates · review a feature: `specs/<feature>/` |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | ✅ tested with v2.2.0 · review a change: `openspec/changes/<change>/`, with ADDED / MODIFIED / REMOVED / RENAMED requirements tagged |
| Any folder of Markdown | ✅ generic adapter; the LLM does the analysis |
| Kiro, BMAD | 🛣️ wanted: [add an adapter](CONTRIBUTING.md#add-an-sdd-framework-adapter) |

**Coding agents** through [Agent Skills](https://agentskills.io). Your agent is the LLM; no API key needed.

| Agent | Status |
|---|---|
| Claude Code | ✅ tested end to end |
| GitHub Copilot (VS Code), OpenAI Codex, Cursor, Gemini CLI | 🧪 experimental: follows each agent's format, not yet reported in a full run |

**Without an agent** (CI): any model [LiteLLM](https://docs.litellm.ai/docs/providers) supports, with your API key.
See [In CI](docs/setup.md#in-ci).

**Podcast voices**, all generated locally: system voices on macOS, Windows and Linux, or natural voices with
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) in 8 languages. See [Voices](docs/podcast.md#voices).

## How it works

```
spec folder ──adapter──▶ common model ──▶ prompt ──▶ your agent (or an API model) ──▶ JSON ──▶ review page
(spec-kit, OpenSpec...)  (every item has file:line)                                  (contract)  (+ podcast)
```

The CLI does the deterministic work: parsing the spec, validating citations, rendering. Your agent does the
interpretation. Whatever the framework or the model, the answer follows a published, versioned contract:
[`insights.v1`](schemas/insights.v1.schema.json) for the review and [`podcast.v1`](schemas/podcast.v1.schema.json)
for the podcast script, with [examples](schemas/examples/). Breaking changes get a new version file.

The full flow, step by step, is diagrammed in [CONTRIBUTING.md](CONTRIBUTING.md#how-it-works).

## Roadmap

Shipped: **v0.1** (attention-ranked review, agent mode) and **v0.2** (spec podcast with tones and voices on
every OS). What comes next is tracked on GitHub, by
[milestone](https://github.com/josluimg/unboringspec/milestones): visuals and diffs between spec iterations,
a conversational review, more frameworks, a PR Action and a PyPI release.
Looking for a place to start? See the [`help wanted`](https://github.com/josluimg/unboringspec/labels/help%20wanted) issues.

## Contributing

New framework adapters, agent integrations and voice engines are the most valuable contributions.
Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
