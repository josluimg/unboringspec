# unboringspec

**Specs your brain actually wants to review.**

Spec-Driven Development (SDD) moved the bottleneck. Agents now write the code, and humans spend
their day reading long specs, plans, research notes and task lists. That is exhausting, and the
important parts (the decisions that actually need a human) get lost in the volume.

`unboringspec` turns an SDD spec folder into a review page built around **human attention**:

1. **30-second summary.** What is being built, in five bullets.
2. **Needs your judgment.** Only the items blocked on a human call: `[NEEDS CLARIFICATION]` markers,
   unresolved trade-offs, gaps a careful reviewer would raise.
3. **Decision cards.** Each decision with its rationale, the alternatives it beat and its risk.
   You approve it or question it.
4. **Progressive disclosure.** Routine decisions, stories, tasks and requirements stay collapsed.
5. **Traceability.** Every claim links to the exact `file:line` it came from. Click it and the source
   opens beside the summary. Citations that do not exist are dropped.
6. **Feedback loop.** Export your verdicts as `review.md` and hand it back to your agent.
7. **🎧 Spec podcast.** Prefer to listen? Two hosts, a guide and a skeptic, talk the spec through in
   about five minutes, voiced locally. The player and the transcript sit at the top of the review page.

It works with the SDD framework you use (through **adapters**) and the coding agent you already have
(through **integrations**). No extra API key is needed when you work inside your IDE.

---

## Where are you?

### 🧑‍💻 In your IDE with a coding agent (recommended)

Your agent (Claude Code, GitHub Copilot, Codex, Cursor, Gemini CLI) **is** the LLM. unboringspec
installs a skill into your project; the agent runs the CLI, does the analysis and renders the page.

```bash
uv tool install git+https://github.com/josluimg/unboringspec   # or: pipx install git+...
cd your-project
unboring init --ai claude        # or copilot, codex, cursor, gemini (repeat --ai for several)
```

Then, in your agent's chat:

```text
/unboring-review specs/001-my-feature
```

or just *"review the spec in specs/001-my-feature"*. You get `.unboring/001-my-feature/review.html`.
Review it, click **Export review.md**, and give that file back to the agent to update the spec.

**Rather listen?** Ask for the podcast, in the language you want:

```text
/unboring-podcast specs/001-my-feature es
```

The agent writes the script (building on the review if you did it), the CLI voices it locally and adds a
player to `review.html`. Voices: see [Podcast voices](#podcast-voices).

<details>
<summary>What happens under the hood</summary>

```
unboring prompt specs/001   →  .unboring/001/prompt.md   (instructions + JSON schema + line-numbered docs)
agent reads it, writes      →  .unboring/001/insights.json
unboring render specs/001   →  validates citations, writes .unboring/001/review.html
```

The CLI does the deterministic parts (parsing, citation checks, rendering). The agent does the
interpretation, with the context of your repository. `init` also adds `.unboring/` to `.gitignore`.
</details>

### ⚙️ In CI

No agent in CI, so the CLI calls a model directly through [LiteLLM](https://docs.litellm.ai/docs/providers)
(Anthropic, OpenAI, Azure, Bedrock, Ollama...). Set the provider's API key as a secret.

```bash
pip install "unboringspec[llm] @ git+https://github.com/josluimg/unboringspec"
unboring review specs/001-my-feature --model anthropic/claude-sonnet-5-5
```

<details>
<summary>Example GitHub Actions workflow</summary>

```yaml
name: Spec review
on:
  pull_request:
    paths: ["specs/**"]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install "unboringspec[llm] @ git+https://github.com/josluimg/unboringspec"
      - name: Review changed specs
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          for d in $(git diff --name-only origin/${{ github.base_ref }} -- specs | cut -d/ -f1-2 | sort -u); do
            unboring review "$d"
          done
      - uses: actions/upload-artifact@v4
        with: { name: spec-review, path: .unboring/ }
```

A ready-made GitHub Action that comments the summary on the PR is on the roadmap.
</details>

### ⚡ Quick try, no LLM at all

```bash
git clone https://github.com/josluimg/unboringspec && cd unboringspec
python -m venv .venv && source .venv/bin/activate && pip install -e .
unboring review examples/speckit/specs/001-photo-albums --offline --open
```

Offline mode only extracts what the framework structure guarantees (stories, requirements, tasks,
clarification markers, recorded decisions). It is useful to see the page, not to replace a review.

---

## The contract

Whatever the SDD framework and whatever the LLM, agents answer in a published format (JSON Schema 2020-12):

| Contract | What the agent writes | Schema |
|---|---|---|
| Review analysis | `insights.json` | [`schemas/insights.v1.schema.json`](schemas/insights.v1.schema.json) |
| Podcast script | `podcast.json` | [`schemas/podcast.v1.schema.json`](schemas/podcast.v1.schema.json) |

```
any framework ──adapter──▶ Spec IR ──▶ same prompt ──▶ any agent or model ──▶ insights.json ──▶ review page
                                                                              (the contract)
```

- Adapters absorb the differences between frameworks; the prompt and the contract do not change.
- Claude Code, Copilot, Codex, Cursor, Gemini and API mode all return the same JSON.
- The schema is embedded in every prompt, so agents do not need this repository to follow it.
  Print them with `unboring schema` and `unboring schema podcast`.
- [`schemas/examples/`](schemas/examples/) has a valid response of each for the example spec
  (the podcast one is in Spanish).

Every decision, risk and question must cite at least one `file:line`. The renderer is lenient where the
schema is strict: an item whose citations do not exist is dropped and reported, not fatal to the review.

The version is in the file name. Breaking changes (removed or renamed fields, new required fields)
get a new file (`insights.v2.schema.json`); additive optional fields keep the same version.

## Support

### SDD frameworks (adapters)

Frameworks evolve, so each adapter states the version its parsing rules were tested against.
If a document exists but nothing parses, unboringspec warns that the template may have changed
instead of silently showing an empty review.

| Framework | Adapter | Tested with | Status |
|---|---|---|---|
| [spec-kit](https://github.com/github/spec-kit) | `spec-kit` | v1.4.4 templates | ✅ supported |
| Any folder of Markdown | `generic` | n/a, the LLM does the analysis | ✅ supported |
| Kiro | | | 🛣️ wanted, [contribute](CONTRIBUTING.md#add-an-sdd-framework-adapter) |
| OpenSpec | | | 🛣️ wanted |
| BMAD | | | 🛣️ wanted |

`unboring adapters` lists them with their tested version.

### Coding agents (integrations)

Most agents now read [Agent Skills](https://agentskills.io) (`SKILL.md`); only the folder differs.
Folders follow the same conventions spec-kit uses.

| Agent | `--ai` | Installs to | Status |
|---|---|---|---|
| Claude Code | `claude` | `.claude/skills/unboring-review/` | ✅ tested end to end |
| GitHub Copilot (VS Code) | `copilot` | `.github/skills/unboring-review/` | 🧪 experimental |
| OpenAI Codex | `codex` | `.agents/skills/unboring-review/` | 🧪 experimental |
| Cursor | `cursor` | `.cursor/skills/unboring-review/` | 🧪 experimental |
| Gemini CLI | `gemini` | `.gemini/commands/unboring.review.toml` | 🧪 experimental |
| Others reading `.agents/skills` | `agents` | `.agents/skills/unboring-review/` | 🧪 experimental |

For Claude Code the skill declares `allowed-tools: Bash(unboring:*)`, so the agent runs the `unboring`
CLI without asking each time; any other command still asks.

*Experimental* means the file follows the agent's documented format but nobody has reported a full run yet.
Tried it? Open an issue or PR to mark it tested.

### Podcast voices

Voices are generated on your machine. Nothing is sent to a TTS service.

| Engine | Quality | Install | Languages |
|---|---|---|---|
| `kokoro` | Natural ([Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) via ONNX) | `podcast` extra + `unboring podcast setup` (downloads ~336 MB once) | en, es, fr, it, pt, hi, ja, zh |
| `say` | Robotic but clear | Nothing, built into macOS | Any voice installed in macOS |

```bash
# Kokoro needs Python 3.10 to 3.13; uv fetches a compatible Python for the tool if needed
uv tool install --python 3.12 "unboringspec[podcast] @ git+https://github.com/josluimg/unboringspec"
unboring podcast setup              # downloads the model into ~/.cache/unboringspec/kokoro
unboring podcast engines --lang es  # what is ready, and the default voices
```

`--engine auto` (default) uses Kokoro when it is ready and falls back to macOS voices. Override voices with
`--voice-guide` / `--voice-skeptic`, and the pace with `--speed`. With ffmpeg installed you get an MP3;
without it, a WAV.

## Commands

| Command | What it does |
|---|---|
| `unboring init --ai <agent>` | Install the review and podcast skills into your agent. |
| `unboring prompt <folder>` | Agent mode, step 1: write the analysis prompt. |
| `unboring render <folder>` | Agent mode, step 2: validate the agent's JSON and build the page. |
| `unboring review <folder>` | One shot with an API key (`--model`), or `--offline`. |
| `unboring podcast prompt <folder>` | Podcast, step 1: write the script prompt (`--lang es`). |
| `unboring podcast render <folder>` | Podcast, step 2: validate the script, voice it, add the player. |
| `unboring podcast setup` / `engines` | Download the Kokoro model / list voice engines. |
| `unboring schema [insights\|podcast]` | Print a contract (JSON Schema). |
| `unboring adapters` / `agents` | List supported frameworks and agents. |

Common options: `--lang` (output language, default: same as the spec), `--adapter` (force one),
`--out` (HTML path), `--open` (open in the browser). Default model for API mode:
`anthropic/claude-sonnet-5-5`, override with `--model` or `$UNBORING_MODEL`.

## Roadmap

- [x] v0.1: spec-kit adapter, attention-ranked review page, traceability, `review.md` export
- [x] v0.1: agent mode (no API key) with integrations for Claude Code, Copilot, Codex, Cursor, Gemini
- [x] v0.2: **Spec podcast**: a guide and a skeptic talk the spec through. The agent writes the script,
      [Kokoro](https://github.com/hexgrad/kokoro) or macOS voices read it locally, the review page plays it
- [ ] v0.2.x: podcast in API mode for CI, more TTS engines (Piper, Chatterbox), chapter markers
- [ ] v0.3: Visuals (user journey, sequence, data model, task dependency graph) and a **diff between spec iterations**
- [ ] v0.4: Conversational review: the agent asks you the 5 questions that matter
- [ ] v0.5: Kiro and OpenSpec adapters, GitHub Action that comments on PRs, publish to PyPI

## Contributing

New framework adapters and agent integrations are the most valuable contributions.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
