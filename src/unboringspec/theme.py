"""Custom styles for the review page (#26).

A theme is a CSS file in the project, `unboring.css`, found automatically by `review`, `render`
and `podcast render` (or given with `--theme`). It sets the page's tokens, CSS custom properties,
for light and for dark, written the usual way:

    :root { --accent: #0b5fff; }
    @media (prefers-color-scheme: dark) { :root { --accent: #7aa7ff; } }

and may add any other CSS. The stylesheet is inlined, so the page stays a single file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

THEME_FILE = "unboring.css"
MAX_BYTES = 100_000

# name: (light, dark, what it is). The template builds its defaults from this table, and
# `unboring theme init` writes it out, so the two never disagree.
TOKENS: dict[str, tuple[str, str, str]] = {
    "bg": ("#f5f7f8", "#0f151b", "page background"),
    "surface": ("#ffffff", "#17202a", "cards and panels"),
    "ink": ("#16222c", "#e8eef3", "main text"),
    "muted": ("#56626e", "#9eacb8", "secondary text"),
    "line": ("#dde3e8", "#26323e", "borders"),
    "accent": ("#2d618a", "#86b4da", "links, buttons, highlights"),
    "accent-ink": ("#ffffff", "#0d1a26", "text on accent buttons"),
    "accent-soft": ("#e6eef5", "#1a2c3c", "accent backgrounds (source chips, podcast box)"),
    "marker": ("#bbd524", "#5d6b12", "highlighter: under section titles, and selected text"),
    "decide": ("#b42318", "#ff8a80", "\"needs your judgment\": text"),
    "decide-soft": ("#fdecea", "#3a1f1d", "\"needs your judgment\": background"),
    "review": ("#8a5d00", "#f5c451", "\"worth a look\" and warnings: text"),
    "review-soft": ("#fff6db", "#352c14", "\"worth a look\" and warnings: background"),
    "routine": ("#3f6b4e", "#8fd0a6", "routine decisions: text"),
    "routine-soft": ("#e8f3ec", "#1b2e22", "routine decisions: background"),
    "hl": ("#e6f0a3", "#3d4510", "highlighted line in the source viewer"),
    "font": ('-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif', "", "text font"),
    "mono": ("ui-monospace, SFMono-Regular, Menlo, monospace", "", "code font"),
    "radius": ("12px", "", "corner radius of cards"),
}

LIGHT = ':root'
DARK_SYSTEM = ':root:not([data-theme="light"])'  # dark by system setting, unless forced light
DARK_FORCED = ':root[data-theme="dark"]'  # dark forced by an embedding page (the demo)
DARK_MEDIA = re.compile(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{", re.I)


class ThemeError(ValueError):
    """The stylesheet cannot be used safely."""


@dataclass
class Theme:
    path: Path
    css: str  # ready to inline
    warnings: list[str] = field(default_factory=list)


def default_tokens(dark: bool = False) -> str:
    """Declarations for the template's default blocks."""
    pairs = [(k, (d if dark else l)) for k, (l, d, _) in TOKENS.items()]
    return " ".join(f"--{k}: {v};" for k, v in pairs if v)


def find(start: Path | None = None) -> Path | None:
    """unboring.css in the current folder or a parent, up to the repository root."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        candidate = folder / THEME_FILE
        if candidate.is_file():
            return candidate
        if (folder / ".git").exists():
            break
    return None


def check(css: str) -> None:
    """CSS only: nothing that could leave the <style> element or load from an insecure place."""
    if len(css.encode("utf-8")) > MAX_BYTES:
        raise ThemeError(f"it is larger than {MAX_BYTES // 1000} KB")
    if "<" in css:
        raise ThemeError("it contains '<'; a stylesheet never needs it, and it could close the <style> element")
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"@import\s+(?:url\(\s*)?['\"]?([^'\")\s;]+)", plain, re.I):
        if not m.group(1).lower().startswith("https://"):
            raise ThemeError(f"@import of {m.group(1)!r}: only https:// URLs are allowed")
    for m in re.finditer(r"url\(\s*['\"]?([^'\")\s]*)", plain, re.I):
        target = m.group(1).lower()
        if not target.startswith(("https://", "data:", "#")):
            raise ThemeError(
                f"url({m.group(1)}): only https:// and data: URLs work, since the page is a single file "
                "opened from anywhere"
            )
    if re.search(r"expression\s*\(|javascript:|behavior\s*:", plain, re.I):
        raise ThemeError("it contains script-like CSS (expression, javascript:, behavior)")
    if plain.count("{") != plain.count("}"):
        raise ThemeError("its braces do not balance")


def _block(css: str, open_brace: int) -> int:
    """Index just after the brace that closes the block opened at open_brace."""
    depth = 0
    for i in range(open_brace, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(css)


def _scope(rules: str, root: str) -> str:
    """Rewrite each rule's selectors so they apply under `root` (:root becomes root itself)."""
    out, i = [], 0
    for m in re.finditer(r"([^{}]+)\{", rules):
        if m.start() < i:
            continue
        end = _block(rules, m.end() - 1)
        selectors = []
        for sel in m.group(1).split(","):
            sel = sel.strip()
            if sel.startswith("@"):  # a nested at-rule: leave it alone
                selectors = None
                break
            selectors.append(root + sel[5:] if sel.startswith(":root") else f"{root} {sel}")
        body = rules[m.end() - 1:end]
        out.append((", ".join(selectors) if selectors is not None else m.group(1).strip()) + " " + body)
        i = end
    return "\n".join(out)


def compile_css(css: str) -> str:
    """Make the dark part of the theme follow the page's own rules.

    Authors write dark tokens in `@media (prefers-color-scheme: dark)`. On the page, dark also
    has to give way when an embedding page forces light, and apply when it forces dark, so each
    such block becomes two: one for the system setting and one for a forced dark theme.
    """
    out, pos = [], 0
    for m in DARK_MEDIA.finditer(css):
        if m.start() < pos:
            continue
        end = _block(css, m.end() - 1)
        inner = css[m.end():end - 1]
        out.append(css[pos:m.start()])
        out.append(f"@media (prefers-color-scheme: dark) {{\n{_scope(inner, DARK_SYSTEM)}\n}}\n{_scope(inner, DARK_FORCED)}")
        pos = end
    out.append(css[pos:])
    return "".join(out)


# --- contrast ---------------------------------------------------------------------


def _declared(css: str, dark: bool) -> dict[str, str]:
    """Token values the theme sets for :root, in light or in dark."""
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    parts, pos, dark_parts = [], 0, []
    for m in DARK_MEDIA.finditer(plain):
        if m.start() < pos:
            continue
        end = _block(plain, m.end() - 1)
        parts.append(plain[pos:m.start()])
        dark_parts.append(plain[m.end():end - 1])
        pos = end
    parts.append(plain[pos:])
    values: dict[str, str] = {}
    for chunk in (dark_parts if dark else parts):
        for m in re.finditer(r"(?:^|[};])\s*:root\s*\{([^}]*)\}", chunk):
            for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+)", m.group(1)):
                values[name] = value.strip()
    return values


def _rgb(value: str) -> tuple[float, float, float] | None:
    v = value.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+).*\)", v)
    if m:
        return tuple(int(x) / 255 for x in m.groups())
    return None  # named colours, hsl(), variables: not checked


def contrast(a: str, b: str) -> float | None:
    ca, cb = _rgb(a), _rgb(b)
    if ca is None or cb is None:
        return None

    def lum(c):
        lin = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(ca), lum(cb)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


PAIRS = [("ink", "bg"), ("ink", "surface"), ("muted", "bg"), ("muted", "surface"), ("accent", "surface"),
         ("accent-ink", "accent"), ("decide", "decide-soft"), ("review", "review-soft"), ("routine", "routine-soft"),
         ("ink", "marker"), ("ink", "hl")]


def contrast_warnings(css: str) -> list[str]:
    """Text that would fall below WCAG AA (4.5:1) with this theme."""
    found = []
    for dark in (False, True):
        tokens = {k: (d if dark else l) for k, (l, d, _) in TOKENS.items()}
        if dark:
            tokens.update({k: v for k, v in _declared(css, False).items() if k not in TOKENS or not TOKENS[k][1]})
        tokens.update(_declared(css, dark))
        for fg, bg in PAIRS:
            ratio = contrast(tokens.get(fg, ""), tokens.get(bg, ""))
            if ratio is not None and ratio < 4.5:
                mode = "dark" if dark else "light"
                found.append(f"{mode}: --{fg} on --{bg} has contrast {ratio:.1f}:1 (AA asks for 4.5:1)")
    return found


def load(path: Path) -> Theme:
    css = path.read_text(encoding="utf-8")
    check(css)
    return Theme(path=path, css=compile_css(css), warnings=contrast_warnings(css))


def starter() -> str:
    """What `unboring theme init` writes: every token, commented out at its default."""
    def line(k: str, v: str, what: str) -> str:
        code = f"  /* --{k}: {v}; */"
        return f"{code:<36}  /* {what} */" if len(code) <= 36 else f"  /* {what}: */\n{code}"

    light = "\n".join(line(k, l, what) for k, (l, _, what) in TOKENS.items())
    dark = "\n".join(f"    /* --{k}: {d}; */" for k, (_, d, _) in TOKENS.items() if d)
    return f"""/* unboringspec theme: the look of every review page in this project.
 *
 * unboring review / render / podcast render pick this file up automatically from the folder
 * you run them in (or a parent, up to the repository root). Commit it so the team shares it.
 *
 * Uncomment and change what you need; anything left out keeps the default. The dark block
 * applies when the reader's system is in dark mode. You can add any other CSS below; it is
 * inlined in the page. Fonts must be installed on the reader's machine or loaded with an
 * https:// @import (e.g. Google Fonts), and images must be https:// or data: URLs.
 */

:root {{
{light}
}}

@media (prefers-color-scheme: dark) {{
  :root {{
{dark}
  }}
}}
"""
