# Live demo

A static site that shows unboringspec's output without installing anything: for each example spec, a
**Before** view (the spec as raw Markdown files, in an editor-like page) and an **After** view (the real
`review.html`, with its diagrams and podcast). Nothing is generated in the browser; the pages are built here.

| Demo | Spec | Podcast |
|---|---|---|
| `site/speckit/` | [spec-kit example](../examples/speckit/specs/001-photo-albums/) | Spanish, casual tone |
| `site/openspec/` | [OpenSpec example](../examples/openspec/openspec/changes/add-invite-link-revocation/) | English, roast tone |

```
demo/
  build.py          rebuilds site/ from the repository's examples
  templates/        the Before / After page and the landing page
  site/             what Vercel serves (committed as built)
    index.html      landing page
    <demo>/
      insights.json, podcast.json   the agent's output (inputs, edited by hand)
      podcast.mp3, podcast.md       the recorded episode and its transcript
      review.html                   the real unboringspec page
      index.html                    the Before / After view
```

## Deploy on Vercel

1. In Vercel, **Add New → Project** and import the `josluimg/unboringspec` repository.
2. **Root Directory**: `demo/site`.
3. **Framework Preset**: *Other*. Leave the build command and output directory empty: the folder is already
   the site.
4. Deploy. Every push to `main` that touches `demo/site/` redeploys it.

## Rebuild

After changing an example spec, the analysis (`insights.json`), a script (`podcast.json`) or the templates:

```bash
python demo/build.py            # re-render the pages, keep the existing audio
python demo/build.py --voice    # also re-record the episodes (needs Kokoro: unboring podcast setup)
```

The build fails if any item in `insights.json` cites a line that does not exist, so the demo cannot drift
from the example specs unnoticed. `--voice` needs the `podcast` extra and the Kokoro model; use
`--engine system` to try it with your system voices.
