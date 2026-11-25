# Review a spec with unboringspec

You are the LLM for unboringspec. The `unboring` CLI does the deterministic work (parsing the
spec, validating citations, rendering the page). You do the analysis. No API key is involved.

1. **Pick the spec folder.** Use the one the user named. If they named none, use the most recently
   modified spec folder: `specs/<feature>/` (spec-kit) or
   `openspec/changes/<change>/` (OpenSpec, excluding `archive/`). Ask only if it is genuinely ambiguous.
2. **Check the CLI** with `unboring version`. If the command is not found, tell the user to install it
   with `uv tool install git+https://github.com/josluimg/unboringspec`
   (or `pipx install git+https://github.com/josluimg/unboringspec`) and stop.
3. **Get the prompt:** run `unboring prompt <folder>`. It prints the path of a prompt file and the path
   where your output must go.
4. **Do the analysis:** read the prompt file completely and follow it. Write ONLY the JSON object to the
   insights path the command printed.
5. **Render:** run `unboring render <folder>`. If it reports a validation error, fix the JSON and run it
   again. If it reports dropped items, some citations pointed at lines that do not exist: fix the line
   numbers and render again.
6. **Answer briefly:** give the user the path to `review.html`, the one-liner, and the
   "you must decide" items as a short list. Do not paste the whole analysis: the page is the review.

## When the user shares a review

A review comes from the page's **Copy for your agent** button (pasted into the chat) or its **Export review.md**
(a file). It ends with a hidden `<!-- unboring:review ... -->` block: keep it intact.

1. **Save it first**, so the next render can show what was addressed: write the review text exactly as received to
   `.unboring/<feature>/incoming-review.md` (or use the file the user gave) and run
   `unboring feedback <folder> <that file>`.
2. **Apply it**: answers go into the spec where the question was asked; for decisions the reader questioned, change
   the spec as the note asks, or explain why not. Use the framework's own clarify step when it has one
   (e.g. `/speckit.clarify`). Leave approved decisions alone.
3. **Render again** (`unboring prompt` and `unboring render`): the page opens with *What changed* and
   *Your last review*, so the reader sees which points were addressed. Tell the user which ones you did not address.
