# unboringspec

**Specs your brain actually wants to review.**

Spec-Driven Development (SDD) moved the bottleneck. Agents now write the code, and humans spend
their day reading long specs, plans, research notes and task lists. That is exhausting, and the
important parts (the decisions that actually need a human) get lost in the volume.

`unboringspec` turns an SDD spec folder into a review experience built around **human attention**:

1. **30-second summary.** What is being built, in five bullets.
2. **Needs your judgment.** Only the items that are blocked on a human call: `[NEEDS CLARIFICATION]`
   markers, unresolved trade-offs, risky choices.
3. **Decision cards.** Each decision with its rationale, the alternatives it beat, and its risk. You
   approve it or question it.
4. **Progressive disclosure.** Routine decisions, stories, tasks and requirements stay collapsed until
   you want them.
5. **Traceability.** Every claim links to the exact `file:line` it came from. Click it and the source
   opens beside the summary. Citations the LLM invents are dropped.
6. **Feedback loop.** Export your verdicts as `review.md` and hand it back to your agent
   (for example in `/speckit.clarify`).

Framework-agnostic by design: adapters parse each SDD flavour into a common model.

| Framework | Status |
|---|---|
| [spec-kit](https://github.com/github/spec-kit) | ✅ supported |
| Any folder of Markdown (Kiro, OpenSpec, BMAD, hand-written) | ✅ generic adapter, LLM does the work |
| Kiro, OpenSpec native adapters | 🛣️ planned, contributions welcome |

## Quick start

```bash
pip install "unboringspec[llm]"
export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY, or run Ollama locally
unboring review specs/001-my-feature --open
```

No API key? Try the offline mode, which uses deterministic extraction only:

```bash
unboring review specs/001-my-feature --offline --open
```

### Options

| Flag | Meaning |
|---|---|
| `--model`, `-m` | Any [LiteLLM](https://docs.litellm.ai/docs/providers) model id. Default `anthropic/claude-sonnet-5-5`, or `$UNBORING_MODEL`. Example: `ollama/qwen3`, `openai/gpt-5`. |
| `--lang` | Output language. Defaults to the language of the spec. |
| `--offline` | No LLM call. |
| `--adapter` | Force an adapter (`spec-kit`, `generic`). |
| `--out`, `-o` | Output path. Default `<spec folder>/review.html`. |

## Try it on the example

```bash
git clone https://github.com/<you>/unboringspec && cd unboringspec
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,llm]"
unboring review examples/speckit/specs/001-photo-albums --offline --open
```

## How it works

```
spec folder ──▶ adapter ──▶ Spec IR ──▶ insights (heuristic | LLM) ──▶ review.html ──▶ review.md
               (deterministic)   (typed, every item has file:line)       (human)       (back to agent)
```

- `adapters/` holds one adapter per framework. They only extract what the framework guarantees
  (stories, requirements, tasks, markers).
- `insights.py` asks the LLM where human attention is needed and validates every citation against the documents.
- `render.py` and `templates/` produce a single self-contained HTML file: no server, easy to attach to a PR.

## Roadmap

- [x] v0.1: spec-kit adapter, attention-ranked review page, traceability, `review.md` export
- [ ] v0.2: **Spec podcast**. Two hosts discuss the spec, one enthusiastic and one skeptical, voiced with
      [Kokoro](https://github.com/hexgrad/kokoro) (Spanish and English) or another pluggable TTS
- [ ] v0.3: Visuals (user journey, sequence, data model, task dependency graph) and **diff between spec iterations**
- [ ] v0.4: Conversational review: the agent asks you the 5 questions that matter
- [ ] v0.5: Native Kiro and OpenSpec adapters, GitHub Action that comments the summary on PRs

## Contributing

Adapters for other SDD frameworks are the most valuable contribution. Look at
`src/unboringspec/adapters/speckit.py` and add a sibling. Run the tests with `pytest`.

## License

MIT
