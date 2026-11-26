"""Custom styles for the review page: unboring.css in the project (#26)."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.insights import heuristic_insights
from unboringspec.render import render_html
from unboringspec.theme import (
    DARK_FORCED,
    DARK_SYSTEM,
    TOKENS,
    ThemeError,
    check,
    compile_css,
    contrast,
    contrast_warnings,
    find,
    load,
    starter,
)

ROOT = Path(__file__).parent.parent
SPEC = ROOT / "examples/speckit/specs/001-photo-albums"
EXAMPLE = ROOT / "examples/themes/editorial.css"
runner = CliRunner()


def page(theme=None):
    return render_html(heuristic_insights(get_adapter(SPEC).load(SPEC)), theme=theme)


# --- defaults --------------------------------------------------------------------


def test_the_template_takes_its_defaults_from_the_token_table():
    html = page()
    for name, (light, dark, _) in TOKENS.items():
        assert f"--{name}: {light};" in html, name
        if dark:
            assert f"--{name}: {dark};" in html, name
    assert 'id="unboring-theme"' not in html  # no theme: the page is as before


def test_default_colours_meet_aa():
    assert contrast_warnings("") == []


def test_starter_lists_every_token_and_changes_nothing():
    css = starter()
    for name in TOKENS:
        assert f"--{name}:" in css
    check(css)
    assert not re.search(r"^\s*--", re.sub(r"/\*.*?\*/", "", css, flags=re.S), re.M)  # all commented out


# --- applying a theme ------------------------------------------------------------


def test_theme_is_inlined_after_the_defaults():
    html = page(load(EXAMPLE))
    assert html.index("/* Default tokens") < html.index('<style id="unboring-theme">')
    assert "--accent: #0f766e;" in html and "Iowan Old Style" in html
    assert 'themed ? { theme: "base", themeVariables' in html  # diagrams follow the tokens


def test_dark_block_follows_system_and_forced_theme():
    css = compile_css("""
:root { --accent: #111111; }
@media (prefers-color-scheme: dark) {
  :root { --accent: #eeeeee; }
  .card, :root h2 { color: red; }
}
""")
    assert ":root { --accent: #111111; }" in css
    assert f"@media (prefers-color-scheme: dark) {{\n{DARK_SYSTEM} {{ --accent: #eeeeee; }}" in css
    assert f"{DARK_SYSTEM} .card, {DARK_SYSTEM} h2" in css
    assert f"{DARK_FORCED} {{ --accent: #eeeeee; }}" in css and f"{DARK_FORCED} .card, {DARK_FORCED} h2" in css


def test_other_at_rules_are_left_alone():
    css = "@media (max-width: 600px) { h1 { font-size: 1rem; } }\n@font-face { font-family: X; src: url(data:font/woff2;base64,AA); }"
    assert compile_css(css) == css


# --- guardrails ------------------------------------------------------------------


@pytest.mark.parametrize("css", [
    "</style><script>alert(1)</script>",
    "body { background: url(file:///etc/passwd); }",
    "body { background: url('http://example.com/x.png'); }",
    "body { background: url(logo.png); }",
    "@import 'other.css';",
    "@import url(http://example.com/a.css);",
    "a { width: expression(alert(1)); }",
    "a { color: red; ",
    "a{}" * 40_000,
])
def test_unsafe_css_is_refused(css):
    with pytest.raises(ThemeError):
        check(css)


@pytest.mark.parametrize("css", [
    "@import url('https://fonts.googleapis.com/css2?family=Inter&display=swap');",
    "h1 { background: url(https://example.com/logo.svg) no-repeat; }",
    "h1::before { content: url(data:image/svg+xml;base64,PHN2Zy8+); }",
    "/* url(file:///ignored-in-a-comment) */ h1 { color: red; }",
])
def test_safe_css_is_accepted(css):
    check(css)


def test_contrast():
    assert round(contrast("#000", "#fff"), 1) == 21.0
    assert contrast("rebeccapurple", "#fff") is None  # not checked rather than guessed
    found = contrast_warnings(":root { --muted: #bbbbbb; }\n@media (prefers-color-scheme: dark) { :root { --ink: #333; } }")
    assert any(w.startswith("light: --muted on --bg") for w in found)
    assert any(w.startswith("dark: --ink on --bg") for w in found)
    assert contrast_warnings(EXAMPLE.read_text()) == []


# --- finding it, and the CLI -----------------------------------------------------


def test_found_in_a_parent_up_to_the_repository_root(tmp_path):
    (tmp_path / "unboring.css").write_text(":root{}")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "specs").mkdir()
    assert find(repo / "specs") is None  # outside the repository: not ours
    (repo / "unboring.css").write_text(":root{}")
    assert find(repo / "specs") == (repo / "unboring.css").resolve()


def _project(tmp_path, monkeypatch):
    import shutil

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    shutil.copytree(SPEC, tmp_path / "specs/001-photo-albums")
    return tmp_path / ".unboring/001-photo-albums/review.html"


def test_review_picks_up_unboring_css(tmp_path, monkeypatch):
    out = _project(tmp_path, monkeypatch)
    (tmp_path / "unboring.css").write_text(EXAMPLE.read_text())
    r = runner.invoke(app, ["review", "specs/001-photo-albums", "--offline"])
    assert r.exit_code == 0, r.output
    assert "Theme:" in r.output and "--accent: #0f766e;" in out.read_text()


def test_theme_option_overrides_and_unsafe_theme_stops(tmp_path, monkeypatch):
    out = _project(tmp_path, monkeypatch)
    (tmp_path / "unboring.css").write_text(":root { --accent: #123456; }")
    (tmp_path / "other.css").write_text(":root { --accent: #654321; }")
    r = runner.invoke(app, ["review", "specs/001-photo-albums", "--offline", "--theme", "other.css"])
    assert r.exit_code == 0 and "#654321" in out.read_text() and "#123456" not in out.read_text()
    (tmp_path / "unboring.css").write_text("</style>")
    r = runner.invoke(app, ["review", "specs/001-photo-albums", "--offline"])
    assert r.exit_code == 2 and "not used" in r.output


def test_theme_init_and_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    assert runner.invoke(app, ["theme", "check"]).exit_code == 1  # nothing to check yet
    assert runner.invoke(app, ["theme", "init"]).exit_code == 0
    assert runner.invoke(app, ["theme", "init"]).exit_code == 1  # never overwrites by accident
    r = runner.invoke(app, ["theme", "check"])
    assert r.exit_code == 0 and "AA" in r.output
    (tmp_path / "unboring.css").write_text(":root { --muted: #cccccc; }")
    assert "Low contrast" in runner.invoke(app, ["theme", "check"]).output
