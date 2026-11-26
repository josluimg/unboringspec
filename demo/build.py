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
from html import escape
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
from unboringspec.theme import load as load_theme  # noqa: E402

REPO_URL = "https://github.com/josluimg/unboringspec"


@dataclass
class Demo:
    slug: str
    spec: str  # folder, relative to the repository
    framework: str
    podcast_note: str  # shown on the landing page
    lang: str  # the spec, the review page, the podcast and the demo's own texts
    theme: str = ""  # a stylesheet from the repository, as unboring.css would be (#48)


DEMOS = [
    Demo("speckit", "examples/speckit-es/specs/001-albumes-compartidos", "spec-kit",
         "All in Spanish · casual podcast", "es"),
    Demo("openspec", "examples/openspec/openspec/changes/add-invite-link-revocation", "OpenSpec · custom theme",
         "Podcast in English · roast tone", "en", theme="examples/themes/corporate.css"),
    Demo("themed", "examples/speckit/specs/001-photo-albums", "spec-kit · custom theme",
         "Podcast in English · sports tone", "en", theme="examples/themes/brutalist.css"),
]

# The demo page's own texts (the review page has its own, in unboringspec.i18n).
UI = {
    "en": {
        "description": "Before: the spec as raw files. After: the same spec as an unboringspec review, with its podcast.",
        "view": "View", "before": "Before", "after": "After",
        "before_label": "Before: the spec as raw files", "after_label": "After: the unboringspec review",
        "files": "Files", "file": "File", "cta": "Make it unboring →",
        "frame": "unboringspec review, with its podcast",
        "stats": "<b>{files}</b> files · <b>{lines}</b> lines · <b>{words}</b> words<br>to read before you can approve anything.",
        "theme": "Switch between light and dark mode",
    },
    "es": {
        "description": "Antes: la spec tal cual, en ficheros. Después: la misma spec como revisión de unboringspec, con su podcast.",
        "view": "Vista", "before": "Antes", "after": "Después",
        "before_label": "Antes: la spec tal cual, en ficheros", "after_label": "Después: la revisión de unboringspec",
        "files": "Ficheros", "file": "Fichero", "cta": "Hazla unboring →",
        "frame": "Revisión de unboringspec, con su podcast",
        "stats": "<b>{files}</b> ficheros · <b>{lines}</b> líneas · <b>{words}</b> palabras<br>que leer antes de poder aprobar nada.",
        "theme": "Cambiar entre modo claro y oscuro",
    },
}

# Light or dark: the system setting until the reader picks one, remembered in this browser.
# Runs in <head> so the page never flashes in the wrong theme.
THEME_HEAD = """<script>
(() => {
  const KEY = "unboring-theme", root = document.documentElement, sys = matchMedia("(prefers-color-scheme: dark)");
  let choice = null;
  try { choice = localStorage.getItem(KEY); } catch (e) {}
  const apply = () => { root.dataset.theme = choice || (sys.matches ? "dark" : "light"); };
  apply();
  sys.addEventListener("change", () => { if (!choice) apply(); });
  window.unboringToggleTheme = () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    choice = next === (sys.matches ? "dark" : "light") ? null : next;  // back to the system's: follow it again
    try { choice ? localStorage.setItem(KEY, choice) : localStorage.removeItem(KEY); } catch (e) {}
    apply();
  };
})();
</script>"""

THEME_BUTTON = (
    '  <button class="theme" type="button" onclick="unboringToggleTheme()" aria-label="{label}" title="{label}">'
    '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
    '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
    'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>'
)


def theme(page: str, lang: str) -> str:
    return page.replace("__THEME_HEAD__", THEME_HEAD).replace("__THEME_BUTTON__", THEME_BUTTON.format(label=UI[lang]["theme"]))


def voice(folder: Path, script_path: Path, documents: dict[str, str], engine_name: str) -> tuple[str, dict]:
    from unboringspec.tts import assemble, pick_engine

    parsed = parse_script(script_path.read_text(encoding="utf-8"))
    turns, problems = validate_script(parsed, documents)
    if problems:
        raise SystemExit(f"{script_path}: {problems}")
    engine = pick_engine(engine_name)
    voices = engine.cast(parsed.language)
    speed = tone_speed(parsed.tone)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, t in enumerate(turns, start=1):
            part = Path(tmp) / f"{i:04d}.wav"
            engine.synth(t.text, voices[t.role], parsed.language, speed, part,
                         terms=[(term.text, term.lang) for term in parsed.terms])
            parts.append(part)
            print(f"  {folder.name}: turn {i}/{len(turns)}", end="\r", flush=True)
        for old in (folder / "podcast.mp3", folder / "podcast.wav"):
            old.unlink(missing_ok=True)
        audio = assemble(parts, folder / "podcast")
    (folder / "podcast.md").write_text(transcript_markdown(parsed, turns), encoding="utf-8")
    print(f"  {folder.name}: {audio.name} recorded with {engine.name} ({voices['guide']} / {voices['skeptic']})")
    return engine.name, voices


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
        used, voices = voice(folder, script, ir.documents, engine)
        kept = {"voices": voices}
    else:
        meta = folder / "podcast.meta.json"
        old = json.loads(meta.read_text()) if meta.exists() else {}
        used = old.get("engine", "kokoro")
        kept = {k: old[k] for k in ("recorded", "voices") if k in old}  # the audio did not change
    tone = parse_script(script.read_text(encoding="utf-8")).tone
    write_podcast_meta(folder, ir.documents, engine=used, tone=tone, **kept)
    style = load_theme(ROOT / demo.theme) if demo.theme else None
    if style and style.warnings:
        raise SystemExit(f"{demo.slug}: {demo.theme}: {style.warnings}")
    write_html(ir, folder / "review.html", demo.lang, style)

    # The "before": the raw documents as they sit in the repository, under their real paths.
    # examples/<example>/<path in that project>
    prefix = demo.spec.split("/", 2)[2] if demo.spec.startswith("examples/") else demo.spec
    files = {f"{prefix}/{name}": text for name, text in ir.documents.items()}
    data = {
        "slug": demo.slug,
        "framework": demo.framework,
        "feature": ir.feature,
        "files": files,
        "repo": REPO_URL,
        "source": f"{REPO_URL}/tree/main/{demo.spec}",
        "lang": demo.lang,
        "ui": {"stats": UI[demo.lang]["stats"]},
    }
    page = (TEMPLATES / "demo.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("__DEMO_TITLE__", f"{demo.framework} · {ir.feature}").replace("__DEMO_DATA__", payload)
    page = theme(page.replace("__LANG__", demo.lang), demo.lang)
    for key, text in UI[demo.lang].items():
        page = page.replace(f"__S_{key}__", escape(text))
    assert "__" not in page.replace("__init__", ""), "placeholder left in demo.html"
    (folder / "index.html").write_text(page, encoding="utf-8")
    lines = sum(len(t.splitlines()) for t in ir.documents.values())
    print(f"✓ {demo.slug}: {len(files)} files, {lines} lines → review.html + index.html")
    return {"slug": demo.slug, "framework": demo.framework, "feature": ir.feature, "files": len(files),
            "lines": lines, "podcast": demo.podcast_note, "one_liner": ir.summary.one_liner if ir.summary else "",
            "theme": Path(demo.theme).name, "lang": demo.lang}


FLAGS = {"es": "🇪🇸", "en": "🇬🇧"}  # the language of each demo, on its landing card


def card_html(c: dict) -> str:
    return (
        f'    <a class="card" href="{c["slug"]}/">\n'
        f'      <span class="fw">{escape(c["framework"])}</span>\n'
        f'      <h2>{escape(c["feature"])}</h2>\n'
        f'      <p>{escape(c["one_liner"])}</p>\n'
        f'      <span class="pill">{FLAGS[c["lang"]]} {escape(c["podcast"])}</span>\n'
        + (f'      <p class="themed">🎨 Same page, your look: this review uses <code>{escape(c["theme"])}</code>, '
           f'one CSS file in the project.</p>\n' if c["theme"] else "")
        + f'      <p class="stats">{c["files"]} files, {c["lines"]} lines of Markdown → one review page.</p>\n'
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
    landing = theme(landing, "en")
    (SITE / "index.html").write_text(landing, encoding="utf-8")
    print("✓ landing: index.html")


if __name__ == "__main__":
    main()
