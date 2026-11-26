"""Rebuild the demo site (demo/site/) from the repository's own examples.

    python demo/build.py            # re-render the pages, keep existing audio
    python demo/build.py --voice    # also re-record the episodes (needs Kokoro: unboring podcast setup)

For each demo, demo/site/<slug>/ holds the agent's output (insights.json, podcast.json); the
script loads the real example spec, applies that output exactly as `unboring render` would, and
writes review.html next to it, plus an index.html with the Before / After toggle. Nothing is
generated in the browser: the demo only shows results.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(__file__).resolve().parent / "site"  # what Vercel serves
TEMPLATES = Path(__file__).resolve().parent / "templates"
sys.path.insert(0, str(ROOT / "src"))

from unboringspec.adapters import get_adapter  # noqa: E402
from unboringspec.insights import apply_insights, parse_insights  # noqa: E402
from unboringspec.podcast import parse_script, tone_speed, transcript_markdown, validate_script  # noqa: E402
from unboringspec.render import write_html, write_podcast_meta  # noqa: E402

REPO_URL = "https://github.com/josluimg/unboringspec"


@dataclass
class Demo:
    slug: str
    spec: str  # folder, relative to the repository
    framework: str
    podcast_note: str  # shown on the landing page


DEMOS = [
    Demo("speckit", "examples/speckit/specs/001-photo-albums", "spec-kit", "Podcast in Spanish · casual tone"),
    Demo("openspec", "examples/openspec/openspec/changes/add-invite-link-revocation", "OpenSpec", "Podcast in English · roast tone"),
]


def voice(folder: Path, script_path: Path, documents: dict[str, str], engine_name: str) -> str:
    from unboringspec.tts import assemble, pick_engine

    parsed = parse_script(script_path.read_text(encoding="utf-8"))
    turns, problems = validate_script(parsed, documents)
    if problems:
        raise SystemExit(f"{script_path}: {problems}")
    engine = pick_engine(engine_name)
    voices = engine.voices(parsed.language)
    speed = tone_speed(parsed.tone)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, t in enumerate(turns, start=1):
            part = Path(tmp) / f"{i:04d}.wav"
            engine.synth(t.text, voices[t.role], parsed.language, speed, part)
            parts.append(part)
            print(f"  {folder.name}: turn {i}/{len(turns)}", end="\r", flush=True)
        for old in (folder / "podcast.mp3", folder / "podcast.wav"):
            old.unlink(missing_ok=True)
        audio = assemble(parts, folder / "podcast")
    (folder / "podcast.md").write_text(transcript_markdown(parsed, turns), encoding="utf-8")
    print(f"  {folder.name}: {audio.name} recorded with {engine.name}")
    return engine.name


def build(demo: Demo, record: bool, engine: str) -> dict:
    spec = ROOT / demo.spec
    folder = SITE / demo.slug
    adapter = get_adapter(spec)
    ir = adapter.load(spec)
    ir.folder = spec.name
    ir, dropped = apply_insights(ir, parse_insights((folder / "insights.json").read_text(encoding="utf-8")), "agent")
    if dropped:
        raise SystemExit(f"{demo.slug}: {dropped} items cite lines that do not exist")

    script = folder / "podcast.json"
    if record or not any((folder / n).exists() for n in ("podcast.mp3", "podcast.wav")):
        used = voice(folder, script, ir.documents, engine)
    else:
        meta = folder / "podcast.meta.json"
        used = json.loads(meta.read_text()).get("engine", "kokoro") if meta.exists() else "kokoro"
    tone = parse_script(script.read_text(encoding="utf-8")).tone
    write_podcast_meta(folder, ir.documents, engine=used, tone=tone)
    write_html(ir, folder / "review.html")

    # The "before": the raw documents as they sit in the repository, under their real paths.
    prefix = demo.spec.split("/", 1)[1] if demo.spec.startswith("examples/") else demo.spec
    prefix = prefix.split("/", 1)[1] if prefix.startswith(("speckit/", "openspec/")) else prefix
    files = {f"{prefix}/{name}": text for name, text in ir.documents.items()}
    data = {
        "slug": demo.slug,
        "framework": demo.framework,
        "feature": ir.feature,
        "files": files,
        "repo": REPO_URL,
        "source": f"{REPO_URL}/tree/main/{demo.spec}",
    }
    page = (TEMPLATES / "demo.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("__DEMO_TITLE__", f"{demo.framework} · {ir.feature}").replace("__DEMO_DATA__", payload)
    (folder / "index.html").write_text(page, encoding="utf-8")
    lines = sum(len(t.splitlines()) for t in ir.documents.values())
    print(f"✓ {demo.slug}: {len(files)} files, {lines} lines → review.html + index.html")
    return {"slug": demo.slug, "framework": demo.framework, "feature": ir.feature, "files": len(files),
            "lines": lines, "podcast": demo.podcast_note, "one_liner": ir.summary.one_liner if ir.summary else ""}


def card_html(c: dict) -> str:
    from html import escape

    return (
        f'    <a class="card" href="{c["slug"]}/">\n'
        f'      <span class="fw">{escape(c["framework"])}</span>\n'
        f'      <h2>{escape(c["feature"])}</h2>\n'
        f'      <p>{escape(c["one_liner"])}</p>\n'
        f'      <span class="pill">🎧 {escape(c["podcast"])}</span>\n'
        f'      <p>{c["files"]} files, {c["lines"]} lines of Markdown → one review page.</p>\n'
        f'      <span class="go">Open the demo →</span>\n'
        f"    </a>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", action="store_true", help="re-record the episodes")
    parser.add_argument("--engine", default="kokoro", help="voice engine for --voice (default: kokoro)")
    args = parser.parse_args()
    cards = [build(d, args.voice, args.engine) for d in DEMOS]
    landing = (TEMPLATES / "landing.html").read_text(encoding="utf-8")
    landing = landing.replace("__CARDS__", "\n".join(card_html(c) for c in cards)).replace("__REPO__", REPO_URL)
    (SITE / "index.html").write_text(landing, encoding="utf-8")
    print("✓ landing: index.html")


if __name__ == "__main__":
    main()
