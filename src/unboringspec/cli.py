from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import __version__
from .adapters import ADAPTERS, get_adapter
from .insights import DEFAULT_MODEL, heuristic_insights, llm_insights
from .render import write_html

app = typer.Typer(
    help="Specs your brain actually wants to review.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def review(
    path: Path = typer.Argument(..., exists=True, file_okay=False, help="Feature spec folder, e.g. specs/001-my-feature"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output HTML file. Default: <path>/review.html"),
    offline: bool = typer.Option(False, "--offline", help="No LLM: deterministic extraction only."),
    model: str = typer.Option(
        os.environ.get("UNBORING_MODEL", DEFAULT_MODEL), "--model", "-m", help="Any LiteLLM model id."
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="Output language (default: same as the spec)."),
    adapter: Optional[str] = typer.Option(None, "--adapter", help="Force an adapter instead of auto-detecting."),
    open_browser: bool = typer.Option(False, "--open", help="Open the result in your browser."),
) -> None:
    """Build a human-friendly review page for one spec folder."""
    ad = get_adapter(path, adapter)
    ir = ad.load(path)
    console.print(f"[bold]{ir.feature}[/] · adapter [cyan]{ad.name}[/] · {len(ir.documents)} documents")

    if offline:
        ir = heuristic_insights(ir)
    else:
        with console.status(f"Asking {model} where your attention is needed..."):
            ir = llm_insights(ir, model=model, lang=lang)

    target = write_html(ir, out or path / "review.html")
    console.print(
        f"[green]✓[/] {target}  "
        f"([red]{len(ir.questions)}[/] open questions, {len(ir.decisions)} decisions, {len(ir.tasks)} tasks)"
    )
    if open_browser:
        webbrowser.open(target.resolve().as_uri())


@app.command()
def adapters() -> None:
    """List supported SDD frameworks."""
    for a in ADAPTERS:
        console.print(f"• {a.name}")


@app.command()
def version() -> None:
    """Show the version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
