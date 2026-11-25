# Setup and usage

Pick the section that matches where you are. The podcast has its own guide: [podcast.md](podcast.md).

- [Install](#install)
- [In your IDE with a coding agent](#in-your-ide-with-a-coding-agent) (recommended)
- [In CI](#in-ci)
- [Quick try, no LLM](#quick-try-no-llm)
- [Command reference](#command-reference)

## Install

unboringspec is a command-line tool, `unboring`. It is not on PyPI yet, so install it from GitHub.
[uv](https://docs.astral.sh/uv/) is the recommended way: it keeps the tool isolated and picks a compatible
Python for you.

```bash
uv tool install git+https://github.com/josluimg/unboringspec
```

Alternatives: `pipx install git+https://github.com/josluimg/unboringspec`, or `pip install` it into a virtual
environment. Check it with `unboring version`.

Optional extras, only if you need them:

| Extra | For | Add it with |
|---|---|---|
| `llm` | [API mode](#in-ci): calling a model directly, e.g. in CI | `uv tool install "unboringspec[llm] @ git+https://github.com/josluimg/unboringspec"` |
| `podcast` | Natural podcast voices (Kokoro) | See [podcast.md](podcast.md#voices); `unboring podcast setup` prints the exact command |

## In your IDE with a coding agent

Your agent (Claude Code, GitHub Copilot, Codex, Cursor, Gemini CLI) **is** the LLM. unboringspec installs a
skill into your project; the agent runs the CLI, does the analysis and renders the page. No API key.

```bash
cd your-project
unboring init --ai claude        # or copilot, codex, cursor, gemini; repeat --ai for several
```

Then, in your agent's chat:

```text
/unboring-review specs/001-my-feature
```

or just *"review the spec in specs/001-my-feature"*. You get `.unboring/001-my-feature/review.html`.
Review it, click **Export review.md**, and give that file back to the agent to update the spec
(for spec-kit, together with `/speckit.clarify`).

What to point it at depends on your framework:

| Framework | Folder to review | Example |
|---|---|---|
| spec-kit | A feature folder | `/unboring-review specs/001-my-feature` |
| OpenSpec | A change (active or archived), or a capability spec | `/unboring-review openspec/changes/add-2fa` |
| Anything else | Any folder of Markdown | `/unboring-review docs/rfcs/042-search` |

`init` also adds `.unboring/` to your `.gitignore`. Add `--podcast` to install the optional podcast skill too.

### Reviewing the next iteration

Each render keeps a snapshot of the analysed spec in `.unboring/<feature>/history/`. When the spec changes,
the next render opens with **What changed**: questions resolved or new, decisions and requirements changed,
stories, entities and tasks added, removed or completed, each linked to its line. It is a semantic diff, not a
text diff: rewording by the agent does not count as a change, while any word changed in the spec does
(`MUST` → `SHOULD` shows up).

To compare with a specific commit instead of the previous render, for example the version that was last
approved:

```bash
unboring render specs/001-my-feature --since main      # or a tag, a commit, HEAD~3...
```

If a snapshot of that exact version exists, its analysis (including the agent's) is used; otherwise that version
is analysed offline, and only what is written in the documents is compared.

### Bringing your review back

On the page, **Copy for your agent** and paste it in the chat (or **Export review.md** and give the file to the agent).
The agent saves it with `unboring feedback`, which prints how to apply it **with your framework's own commands**:
unboringspec reviews, the framework changes the spec. Without an agent:

```bash
unboring feedback specs/001-my-feature ~/Downloads/review.md
```

```text
Apply it with spec-kit's own commands, in this order. Do not edit the spec files directly.
  1. /speckit-clarify · answers and decisions about the spec, recorded under ## Clarifications · 1 answer
     pass the content of .unboring/001-my-feature/apply/1-clarify.md
  2. /speckit-plan · decisions in the plan and research · 1 answer, 1 decision
     pass the content of .unboring/001-my-feature/apply/2-plan.md
  3. /speckit-tasks · regenerate the tasks from the updated spec and plan · no input
```

| Framework | Apply steps |
|---|---|
| spec-kit | `/speckit.clarify` for points in `spec.md`, `/speckit.plan` for the plan and research, then `/speckit.tasks` (and optionally `/speckit.analyze`) |
| OpenSpec | `/opsx:update <change>` with the whole review |
| Anything else | edit the documents directly |

Each point goes to the command that owns the file it cites, and each command gets an input file with only its points,
marked as already decided so the command does not ask them again. The command names follow how the framework was
installed for your agent (`/speckit-clarify` as a skill, `/speckit.clarify` as a command), looked up in the project
and in your home folder; if a command is missing, it says so. `unboring feedback <folder>` without a file prints the
steps again for the last saved review.

On the next render, the page opens with **Your last review**:

| You | In the new version | Shown as |
|---|---|---|
| Answered a question | Resolved | ✅ addressed |
| Answered a question | Still open | ⏳ still open, your answer kept |
| Questioned a decision | Changed | 🔎 check it matches your note |
| Questioned a decision | Unchanged | ⏳ not changed yet, your note kept |
| Approved a decision | Unchanged | ✓ still approved |
| Approved a decision | Changed | ⚠️ approved, then changed: look again |

Marks that still hold are filled in from the saved review, in any browser. Reviews are kept in
`.unboring/<feature>/reviews/`; the latest one is followed up.

### What happens under the hood

```
unboring prompt specs/001   →  .unboring/001/prompt.md   (instructions + JSON schema + line-numbered docs)
agent reads it, writes      →  .unboring/001/insights.json
unboring render specs/001   →  validates citations, writes .unboring/001/review.html
```

The CLI does the deterministic parts (parsing, citation checks, rendering). The agent does the interpretation,
with the context of your repository. A diagram of the whole flow is in [CONTRIBUTING.md](../CONTRIBUTING.md#how-it-works).

### Where each agent finds the skill

| Agent | `--ai` | Installs to | Status |
|---|---|---|---|
| Claude Code | `claude` | `.claude/skills/<skill>/SKILL.md` | ✅ tested end to end |
| GitHub Copilot (VS Code) | `copilot` | `.github/skills/<skill>/SKILL.md` | 🧪 experimental |
| OpenAI Codex | `codex` | `.agents/skills/<skill>/SKILL.md` | 🧪 experimental |
| Cursor | `cursor` | `.cursor/skills/<skill>/SKILL.md` | 🧪 experimental |
| Gemini CLI | `gemini` | `.gemini/commands/unboring.<skill>.toml` | 🧪 experimental |
| Others reading `.agents/skills` | `agents` | `.agents/skills/<skill>/SKILL.md` | 🧪 experimental |

The agent discovers the skill by its name and description, and loads the full instructions when you invoke it
or ask for something that matches. For Claude Code the skill declares `allowed-tools: Bash(unboring:*)`, so the
agent runs the `unboring` CLI without asking each time; any other command still asks.

*Experimental* means the file follows the agent's documented format but nobody has reported a full run yet.

## In CI

There is no agent in CI, so the CLI calls a model directly through [LiteLLM](https://docs.litellm.ai/docs/providers)
(Anthropic, OpenAI, Azure, Bedrock, Ollama...). Set the provider's API key as a secret.

```bash
pip install "unboringspec[llm] @ git+https://github.com/josluimg/unboringspec"
unboring review specs/001-my-feature --model anthropic/claude-sonnet-5-5
```

The default model is `anthropic/claude-sonnet-5-5`; override it with `--model` or `$UNBORING_MODEL`.

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

A ready-made GitHub Action that comments the summary on the PR is planned: [#15](https://github.com/josluimg/unboringspec/issues/15).
</details>

## Quick try, no LLM

```bash
git clone https://github.com/josluimg/unboringspec && cd unboringspec
python -m venv .venv && source .venv/bin/activate && pip install -e .
unboring review examples/speckit/specs/001-photo-albums --offline --open
unboring review examples/openspec/openspec/changes/add-invite-link-revocation --offline --open
```

Offline mode only extracts what the framework structure guarantees (stories, requirements, tasks, clarification
markers, recorded decisions). It is useful to see the page, not to replace a review.

## Command reference

| Command | What it does |
|---|---|
| `unboring init --ai <agent> [--podcast]` | Install the review skill into your agent; `--podcast` adds the optional podcast skill. |
| `unboring prompt <folder>` | Agent mode, step 1: write the analysis prompt. |
| `unboring render <folder>` | Agent mode, step 2: validate the agent's JSON and build the page. |
| `unboring review <folder>` | One shot with an API key (`--model`), or `--offline`. |
| `unboring feedback <folder> <review.md or ->` | Save a review so the next render follows it up. |
| `unboring podcast prompt <folder>` | Podcast, step 1: write the script prompt (`--lang`, `--tone`). |
| `unboring podcast render <folder>` | Podcast, step 2: validate the script, voice it, add the player. |
| `unboring podcast tones` | List the tone presets. |
| `unboring podcast setup` | Guided voice setup: what works here, how to add Kokoro, model download. |
| `unboring podcast engines` | Same report as setup, without downloading anything. |
| `unboring schema [insights\|podcast]` | Print a contract (JSON Schema). |
| `unboring adapters` / `agents` | List supported frameworks and agents. |
| `unboring version` | Show the version. |

Common options: `--lang` (output language, default: same as the spec), `--adapter` (force one), `--out`
(HTML path), `--open` (open in the browser), `--since <git ref>` (compare with that version; `render` and
`review`). Working files go to `.unboring/<feature>/` in the current folder.
