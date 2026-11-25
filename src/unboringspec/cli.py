from __future__ import annotations

import json
import os
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
from pydantic import ValidationError
from rich.console import Console

from . import __version__
from .adapters import ADAPTERS, get_adapter
from .insights import (
    DEFAULT_MODEL,
    apply_insights,
    build_prompt,
    heuristic_insights,
    json_schema,
    llm_insights,
    parse_insights,
)
from .integrations import INTEGRATIONS, install
from .ir import SpecIR
from .render import write_html

app = typer.Typer(
    help=(
        "Specs your brain actually wants to review.\n\n"
        "Agent mode (inside Claude Code, Copilot, Codex...): `unboring init --ai <agent>` once, "
        "then ask your agent to review a spec.\n\n"
        "API mode (CI): `unboring review <folder>` with a provider API key.\n\n"
        "Quick try: `unboring review <folder> --offline`."
    ),
    no_args_is_help=True,
    add_completion=False,
)
# soft_wrap: agents parse this output, so never break paths across lines.
console = Console(soft_wrap=True)

SPEC_ARG = typer.Argument(..., exists=True, file_okay=False, help="Feature spec folder, e.g. specs/001-my-feature")
ADAPTER_OPT = typer.Option(None, "--adapter", help="Force an adapter instead of auto-detecting.")


def _workdir(spec: Path) -> Path:
    """Working files live in .unboring/<feature>/ under the current directory (gitignored)."""
    return Path(".unboring") / spec.resolve().name


def _load(spec: Path, adapter: str | None) -> SpecIR:
    ad = get_adapter(spec, adapter)
    ir = ad.load(spec)
    console.print(f"[bold]{ir.feature}[/] · adapter [cyan]{ad.name}[/] ({ad.tested_with}) · {len(ir.documents)} documents")
    for w in ir.warnings:
        console.print(f"[yellow]⚠ {w}[/]")
    return ir


def _done(ir: SpecIR, target: Path, open_browser: bool) -> None:
    console.print(
        f"[green]✓[/] {target}  "
        f"({len(ir.questions)} open questions, {len(ir.decisions)} decisions, {len(ir.tasks)} tasks)"
    )
    if open_browser:
        webbrowser.open(target.resolve().as_uri())


# --- agent mode ------------------------------------------------------------------


@app.command()
def init(
    ai: List[str] = typer.Option(
        ..., "--ai", help=f"Agent(s) to install into: {', '.join(INTEGRATIONS)}. Repeat for several."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
    root: Path = typer.Option(Path("."), "--root", file_okay=False, help="Project root."),
) -> None:
    """Install the review skill into your coding agent (no API key needed)."""
    unknown = [a for a in ai if a not in INTEGRATIONS]
    if unknown:
        console.print(f"[red]Unknown agent(s): {', '.join(unknown)}.[/] Available: {', '.join(INTEGRATIONS)}")
        raise typer.Exit(2)
    for path, outcome in install(root, ai, force):
        console.print(f"  {path}  [dim]{outcome}[/]")
    console.print("\nNow ask your agent: [bold]review the spec in specs/<feature>[/] (or use /unboring-review).")


@app.command()
def prompt(
    spec: Path = SPEC_ARG,
    lang: Optional[str] = typer.Option(None, "--lang", help="Output language (default: same as the spec)."),
    adapter: Optional[str] = ADAPTER_OPT,
) -> None:
    """Agent mode, step 1: write the analysis prompt for your agent to answer."""
    ir = _load(spec, adapter)
    wd = _workdir(spec)
    wd.mkdir(parents=True, exist_ok=True)
    out = wd / "prompt.md"
    out.write_text(build_prompt(ir, lang, for_agent=True), encoding="utf-8")
    console.print(f"Prompt:   {out}")
    console.print(f"Write to: {wd / 'insights.json'}")
    console.print(f"Then run: unboring render {spec}")


@app.command()
def render(
    spec: Path = SPEC_ARG,
    insights: Optional[Path] = typer.Option(None, "--insights", "-i", help="Insights JSON. Default: .unboring/<feature>/insights.json"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output HTML. Default: .unboring/<feature>/review.html"),
    adapter: Optional[str] = ADAPTER_OPT,
    open_browser: bool = typer.Option(False, "--open", help="Open the result in your browser."),
) -> None:
    """Agent mode, step 2: validate the agent's insights and build the review page."""
    ir = _load(spec, adapter)
    wd = _workdir(spec)
    src = insights or wd / "insights.json"
    if not src.is_file():
        console.print(f"[red]No insights found at {src}.[/] Run `unboring prompt {spec}` and have your agent write it.")
        raise typer.Exit(1)
    try:
        data = parse_insights(src.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as e:
        console.print(f"[red]{src} is not valid insights JSON:[/]\n{e}")
        raise typer.Exit(1)
    ir, dropped = apply_insights(ir, data, "agent")
    if dropped:
        console.print(f"[yellow]⚠ Dropped {dropped} item(s) whose citations point to lines that do not exist.[/]")
    _done(ir, write_html(ir, out or wd / "review.html"), open_browser)


# --- API mode and offline --------------------------------------------------------


@app.command()
def review(
    spec: Path = SPEC_ARG,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output HTML. Default: .unboring/<feature>/review.html"),
    offline: bool = typer.Option(False, "--offline", help="No LLM: deterministic extraction only."),
    model: str = typer.Option(
        os.environ.get("UNBORING_MODEL", DEFAULT_MODEL), "--model", "-m", help="Any LiteLLM model id."
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="Output language (default: same as the spec)."),
    adapter: Optional[str] = ADAPTER_OPT,
    open_browser: bool = typer.Option(False, "--open", help="Open the result in your browser."),
) -> None:
    """One-shot review: calls an LLM API directly (for CI), or --offline."""
    ir = _load(spec, adapter)
    if offline:
        ir = heuristic_insights(ir)
    else:
        try:
            with console.status(f"Asking {model} where your attention is needed..."):
                ir, dropped = llm_insights(ir, model=model, lang=lang)
        except Exception as e:  # provider errors vary a lot; give one actionable message
            console.print(f"[red]LLM call failed:[/] {e}")
            console.print(
                "Working inside an IDE agent? Use agent mode instead, no API key needed: "
                "[bold]unboring init --ai claude|copilot|codex|cursor|gemini[/]\n"
                "Just trying it out? Add [bold]--offline[/]."
            )
            raise typer.Exit(1)
        if dropped:
            console.print(f"[yellow]⚠ Dropped {dropped} item(s) with invented citations.[/]")
    _done(ir, write_html(ir, out or _workdir(spec) / "review.html"), open_browser)


# --- info ------------------------------------------------------------------------


@app.command()
def adapters() -> None:
    """List supported SDD frameworks and the version each adapter is tested with."""
    for a in ADAPTERS:
        console.print(f"• [bold]{a.name}[/]  {a.tested_with}")


@app.command()
def agents() -> None:
    """List coding agents `init --ai` can install into."""
    for i in INTEGRATIONS.values():
        console.print(f"• [bold]{i.key}[/]  {i.label} → {i.target}  [dim]{i.status}[/]")


@app.command()
def schema() -> None:
    """Print the JSON Schema agents must return (the insights contract)."""
    # Plain print: the output is meant to be piped to a file or another tool.
    print(json.dumps(json_schema(), indent=2, ensure_ascii=False))


@app.command()
def version() -> None:
    """Show the version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
