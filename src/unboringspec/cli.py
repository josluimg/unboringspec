from __future__ import annotations

import json
import os
import shutil
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape

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


THEME_OPT = typer.Option(
    None, "--theme", exists=True, dir_okay=False,
    help="Stylesheet for the page. Default: unboring.css in this folder or a parent, if there is one.",
)


def _theme(path: Path | None):
    """The project's theme (#26): --theme, else unboring.css found from here up to the repository root."""
    from .theme import ThemeError, find, load

    path = path or find()
    if path is None:
        return None
    try:
        theme = load(path)
    except ThemeError as e:
        console.print(f"[red]Theme {escape(str(path))} not used: {escape(str(e))}.[/]")
        raise typer.Exit(2)
    console.print(f"Theme: {escape(str(path))}")
    for w in theme.warnings:
        console.print(f"[yellow]⚠ Low contrast in the theme, {escape(w)}[/]")
    return theme


def _workdir(spec: Path) -> Path:
    """Working files live in .unboring/<feature>/ under the current directory (gitignored)."""
    return Path(".unboring") / spec.resolve().name


def _load(spec: Path, adapter: str | None) -> SpecIR:
    ad = get_adapter(spec, adapter)
    ir = ad.load(spec)
    ir.folder = spec.resolve().name
    console.print(f"[bold]{ir.feature}[/] · adapter [cyan]{ad.name}[/] ({ad.tested_with}) · {len(ir.documents)} documents")
    for w in ir.warnings:
        console.print(f"[yellow]⚠ {escape(w)}[/]")
    return ir


SINCE_OPT = typer.Option(
    None, "--since", help="Compare with the spec at this git ref (commit, tag, branch) instead of the previous render."
)


def _with_changes(ir: SpecIR, spec: Path, since: str | None = None, adapter: str | None = None) -> SpecIR:
    """Record this version in the history and attach what changed since the previous one (or `since`)."""
    from .diff import compare, summarize
    from .history import BaselineError, History, git_baseline

    history = History(_workdir(spec))
    try:
        baseline = git_baseline(spec, since, history, adapter) if since else None
    except BaselineError as e:
        console.print(f"[red]--since {escape(since)}: {escape(str(e))}[/]")
        raise typer.Exit(2)
    previous = history.record(ir)
    baseline = baseline or previous
    if baseline is not None:
        ir.changes = compare(baseline[0], ir, baseline[1])
        if since:
            ir.changes.since_ref = baseline[1]
        else:
            ir.changes.since_render = history.previous_when
        console.print(f"Changes since {escape(ir.changes.baseline)}: {summarize(ir.changes)}")
    return _with_follow_up(ir, spec, history)


def _with_follow_up(ir: SpecIR, spec: Path, history) -> SpecIR:
    """Map the reader's last saved review onto this version (#28)."""
    from .feedback import _when, follow_up, latest_review

    found = latest_review(_workdir(spec))
    if found is None:
        return ir
    path, review = found
    ir.follow_up = follow_up(review, _when(path), ir, history)
    if ir.follow_up.same_version:
        console.print(f"Loaded {escape(ir.follow_up.reviewed)} ({len(ir.follow_up.carried)} marks)")
    else:
        counts: dict[str, int] = {}
        for i in ir.follow_up.items:
            counts[i.outcome] = counts.get(i.outcome, 0) + 1
        detail = ", ".join(f"{n} {o}" for o, n in counts.items()) or "nothing to follow up"
        console.print(f"Follow-up of {escape(ir.follow_up.reviewed)}: {detail}")
    return ir


def _done(ir: SpecIR, target: Path, open_browser: bool) -> None:
    from .render import find_podcast

    console.print(
        f"[green]✓[/] {target}  "
        f"({len(ir.questions)} open questions, {len(ir.decisions)} decisions, {len(ir.tasks)} tasks)"
    )
    episode = find_podcast(target.parent, ir)
    if episode and episode["stale"]:
        since = f" ({episode['changes']} changes since)" if episode["changes"] else ""
        console.print(
            f"[yellow]⚠ The podcast on this page is about an earlier version of the spec{since}. "
            f"Record a new one: /unboring-podcast {escape(ir.folder or '<folder>')}[/]"
        )
    if open_browser:
        webbrowser.open(target.resolve().as_uri())


# --- agent mode ------------------------------------------------------------------


@app.command()
def init(
    ai: List[str] = typer.Option(
        ..., "--ai", help=f"Agent(s) to install into: {', '.join(INTEGRATIONS)}. Repeat for several."
    ),
    podcast: bool = typer.Option(
        False, "--podcast", help="Also install the optional podcast skill (voices need the podcast extra)."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
    root: Path = typer.Option(Path("."), "--root", file_okay=False, help="Project root."),
) -> None:
    """Install the review skill into your coding agent (no API key needed)."""
    unknown = [a for a in ai if a not in INTEGRATIONS]
    if unknown:
        console.print(f"[red]Unknown agent(s): {', '.join(unknown)}.[/] Available: {', '.join(INTEGRATIONS)}")
        raise typer.Exit(2)
    for path, outcome in install(root, ai, force, podcast=podcast):
        console.print(f"  {path}  [dim]{outcome}[/]")
    console.print("\nNow ask your agent: [bold]review the spec in specs/<feature>[/] (/unboring-review).")
    if podcast:
        console.print("Or: [bold]make a podcast about it[/] (/unboring-podcast). Check voices with: unboring podcast engines")
    else:
        flags = " ".join(f"--ai {a}" for a in ai)
        console.print(f"[dim]Optional spec podcast: unboring init {flags} --podcast[/]")


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
    since: Optional[str] = SINCE_OPT,
    lang: Optional[str] = typer.Option(None, "--lang", help="Language of the page itself: en (default) or es."),
    theme: Optional[Path] = THEME_OPT,
) -> None:
    """Agent mode, step 2: validate the agent's insights and build the review page."""
    style = _theme(theme)
    ir = _load(spec, adapter)
    wd = _workdir(spec)
    src = insights or wd / "insights.json"
    if not src.is_file():
        console.print(f"[red]No insights found at {src}.[/] Run `unboring prompt {spec}` and have your agent write it.")
        raise typer.Exit(1)
    try:
        data = parse_insights(src.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as e:
        console.print(f"[red]{escape(str(src))} is not valid insights JSON:[/]\n{escape(str(e))}")
        raise typer.Exit(1)
    ir, dropped = apply_insights(ir, data, "agent")
    if dropped:
        console.print(f"[yellow]⚠ Dropped {dropped} item(s) whose citations point to lines that do not exist.[/]")
    ir = _with_changes(ir, spec, since, adapter)
    _done(ir, write_html(ir, out or wd / "review.html", lang or "en", style), open_browser)


@app.command()
def feedback(
    spec: Path = SPEC_ARG,
    review_file: Optional[str] = typer.Argument(
        None, help="The exported review.md, or - for standard input. Omit it to show the steps for the last saved review."
    ),
) -> None:
    """Save a review and print how to apply it with the framework's own commands."""
    import sys

    from .apply import plan_apply
    from .feedback import ReviewError, latest_review, save_review
    from .history import documents_hash

    wd = _workdir(spec)
    if review_file is None:
        found = latest_review(wd)
        if found is None:
            console.print(f"[red]No saved review for {escape(str(spec))}.[/] Pass the exported review.md or - .")
            raise typer.Exit(1)
        path, review = found
    else:
        text = sys.stdin.read() if review_file == "-" else Path(review_file).expanduser().read_text(encoding="utf-8")
        try:
            path, review = save_review(wd, text)
        except ReviewError as e:
            console.print(f"[red]{escape(str(e))}[/]")
            raise typer.Exit(1)
    ad = get_adapter(spec)
    ir = _load(spec, None)
    state = "this version" if review.version == documents_hash(ir.documents) else "an earlier version"
    kinds: dict[str, int] = {}
    for i in review.items:
        kinds[i.kind] = kinds.get(i.kind, 0) + 1
    verb = "Using" if review_file is None else "Saved"
    console.print(f"{verb} {path} · {len(review.items)} points on {state} ({', '.join(f'{n} {k}' for k, n in kinds.items())})")

    steps = plan_apply(review, ir, ad, spec, wd)
    if not steps:
        console.print("Nothing to apply: the review only approves. Render again to keep the approvals.")
        return
    for check in ad.apply_checks(spec):
        console.print(f"\n[yellow]⚠ Before you start: {escape(check)}[/]")
    if steps[0].step.command is None:
        console.print("\nNo framework commands for this spec: edit the documents directly with this input:")
    else:
        console.print(f"\nApply it with {ad.label or ad.name}'s own commands, in this order. [bold]Do not edit the spec files directly.[/]")
    missing = []
    for n, p in enumerate(steps, start=1):
        answers = len([i for i in p.items if i.kind == "answer"])
        notes = len([i for i in p.items if i.kind == "question"])
        parts = [f"{answers} answer{'s' * (answers != 1)}"] * bool(answers) + [f"{notes} decision{'s' * (notes != 1)}"] * bool(notes)
        what = ", ".join(parts) or "no input"
        call = p.invocation or "edit the documents"
        optional = " (optional)" if p.step.optional else ""
        line = f"  {n}. [bold]{escape(call)}[/]{optional} · {escape(p.step.covers)} · {what}"
        if p.input_file:
            line += f"\n     pass the content of {p.input_file}"
        console.print(line)
        if p.step.command is not None and not p.installed and not p.step.optional:
            missing.append(p.step.command)
    if missing:
        console.print(
            f"[yellow]⚠ Not found in this project or your home folder: {escape(', '.join(missing))}.[/] "
            f"Install {ad.label or ad.name} for your agent, or apply the input files by hand."
        )
    console.print(f"Then: unboring prompt {spec} and unboring render {spec} to see what was addressed.")


# --- API mode and offline --------------------------------------------------------


@app.command()
def review(
    spec: Path = SPEC_ARG,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output HTML. Default: .unboring/<feature>/review.html"),
    offline: bool = typer.Option(False, "--offline", help="No LLM: deterministic extraction only."),
    model: str = typer.Option(
        os.environ.get("UNBORING_MODEL", DEFAULT_MODEL), "--model", "-m", help="Any LiteLLM model id."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="Language of the analysis and of the page (en, es); default: the spec's for the analysis, en for the page."
    ),
    adapter: Optional[str] = ADAPTER_OPT,
    open_browser: bool = typer.Option(False, "--open", help="Open the result in your browser."),
    since: Optional[str] = SINCE_OPT,
    theme: Optional[Path] = THEME_OPT,
) -> None:
    """One-shot review: calls an LLM API directly (for CI), or --offline."""
    style = _theme(theme)
    ir = _load(spec, adapter)
    if offline:
        ir = heuristic_insights(ir)
    else:
        try:
            with console.status(f"Asking {model} where your attention is needed..."):
                ir, dropped = llm_insights(ir, model=model, lang=lang)
        except Exception as e:  # provider errors vary a lot; give one actionable message
            console.print(f"[red]LLM call failed:[/] {escape(str(e))}")
            console.print(
                "Working inside an IDE agent? Use agent mode instead, no API key needed: "
                "[bold]unboring init --ai claude|copilot|codex|cursor|gemini[/]\n"
                "Just trying it out? Add [bold]--offline[/]."
            )
            raise typer.Exit(1)
        if dropped:
            console.print(f"[yellow]⚠ Dropped {dropped} item(s) with invented citations.[/]")
    ir = _with_changes(ir, spec, since, adapter)
    _done(ir, write_html(ir, out or _workdir(spec) / "review.html", lang or "en", style), open_browser)


# --- podcast ---------------------------------------------------------------------

podcast_app = typer.Typer(
    help=(
        "Spec podcast: two hosts talk through the spec, a guide and a skeptic.\n\n"
        "Agent mode: `unboring podcast prompt <folder>`, the agent writes podcast.json, "
        "then `unboring podcast render <folder>`."
    ),
    no_args_is_help=True,
)
app.add_typer(podcast_app, name="podcast")


@podcast_app.command("prompt")
def podcast_prompt(
    spec: Path = SPEC_ARG,
    lang: Optional[str] = typer.Option(None, "--lang", help="Script language, e.g. es or en (default: same as the spec)."),
    tone: Optional[str] = typer.Option(
        None, "--tone", "-t", help="A preset (see `unboring podcast tones`) or your own description in quotes."
    ),
    adapter: Optional[str] = ADAPTER_OPT,
) -> None:
    """Step 1: write the script prompt for your agent (uses insights.json if the review was done)."""
    from .podcast import build_podcast_prompt, resolve_tone

    try:
        tone_id = resolve_tone(tone)[0]
    except ValueError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        raise typer.Exit(2)

    ir = _load(spec, adapter)
    wd = _workdir(spec)
    wd.mkdir(parents=True, exist_ok=True)
    insights = wd / "insights.json"
    text = build_podcast_prompt(ir, insights.read_text(encoding="utf-8") if insights.is_file() else None, lang, tone)
    out = wd / "podcast.prompt.md"
    out.write_text(text, encoding="utf-8")
    if not insights.is_file():
        console.print("[dim]No insights.json yet: the script will be based on the spec alone.[/]")
    console.print(f"Tone:     {tone_id}" + (f" ({escape(tone)})" if tone_id == "custom" else ""))
    console.print(f"Prompt:   {out}")
    console.print(f"Write to: {wd / 'podcast.json'}")
    console.print(f"Then run: unboring podcast render {spec}")


@podcast_app.command("render")
def podcast_render(
    spec: Path = SPEC_ARG,
    script: Optional[Path] = typer.Option(None, "--script", help="Script JSON. Default: .unboring/<feature>/podcast.json"),
    engine: str = typer.Option(os.environ.get("UNBORING_TTS", "auto"), "--engine", "-e", help="auto (Kokoro if ready, else system), system, kokoro, say, sapi or espeak."),
    voice_guide: Optional[str] = typer.Option(None, "--voice-guide", help="Pin the guide's voice. With Kokoro also a blend (ef_dora*0.6+em_alex*0.4) and a pitch shift (@-2)."),
    voice_skeptic: Optional[str] = typer.Option(None, "--voice-skeptic", help="Pin the skeptic's voice (same syntax). Default: a pair picked at random from the language's cast."),
    speed: Optional[float] = typer.Option(
        None, "--speed", min=0.5, max=2.0, help="Speech speed (default: the tone's, e.g. faster for sports)."
    ),
    adapter: Optional[str] = ADAPTER_OPT,
    open_browser: bool = typer.Option(False, "--open", help="Open the review page with the player."),
    theme: Optional[Path] = THEME_OPT,
) -> None:
    """Step 2: validate the script, voice it and add a player to the review page."""

    style = _theme(theme)

    from .podcast import parse_script, record_episode, tone_speed, transcript_markdown, validate_script, word_count
    from .tts import EngineUnavailable, pick_engine

    ir = _load(spec, adapter)
    wd = _workdir(spec)
    src = script or wd / "podcast.json"
    if not src.is_file():
        console.print(f"[red]No script found at {src}.[/] Run `unboring podcast prompt {spec}` and have your agent write it.")
        raise typer.Exit(1)
    try:
        parsed = parse_script(src.read_text(encoding="utf-8"))
        turns, problems = validate_script(parsed, ir.documents)
    except (ValidationError, ValueError) as e:
        console.print(f"[red]{escape(str(src))} is not a valid podcast script:[/]\n{escape(str(e))}")
        raise typer.Exit(1)
    for p in problems:
        console.print(f"[yellow]⚠ {escape(p)}[/]")
    if speed is None:
        speed = tone_speed(parsed.tone)

    try:
        tts = pick_engine(engine)
        voices = tts.cast(parsed.language)  # a pair picked at random where the engine has a cast (#61)
    except EngineUnavailable as e:
        console.print(f"[red]{escape(str(e))}[/]")
        raise typer.Exit(1)
    if voice_guide:
        voices["guide"] = voice_guide
    if voice_skeptic:
        voices["skeptic"] = voice_skeptic
    if any("@" in v for v in voices.values()) and not shutil.which("ffmpeg"):
        console.print("[yellow]⚠ Pitch shifts (@) need ffmpeg; those voices keep their own pitch.[/]")
    console.print(
        f"Voicing {len(turns)} turns, {word_count(turns)} words with [cyan]{tts.name}[/] "
        f"(guide: {escape(voices['guide'])}, skeptic: {escape(voices['skeptic'])})"
    )
    if engine == "auto" and tts.tier == "system":
        console.print("[dim]Using system voices. For natural voices: unboring podcast setup[/]")
    terms = [(term.text, term.lang) for term in parsed.terms]
    if terms and tts.tier == "system":
        console.print(
            f"[dim]{len(terms)} terms in another language (e.g. {escape(terms[0][0])}) are read with "
            f"{escape(parsed.language)} rules by system voices; natural voices say them right.[/]"
        )

    with console.status("Recording...") as status:
        def progress(i, total, turn):
            status.update(f"Recording turn {i}/{total} · {turn.name}")

        try:
            audio, seconds, chapters = record_episode(tts, parsed, turns, voices, speed, wd / "podcast", progress)
        except EngineUnavailable as e:
            status.stop()
            console.print(f"[red]{escape(str(e))}[/]")
            raise typer.Exit(1)

    (wd / "podcast.md").write_text(transcript_markdown(parsed, turns), encoding="utf-8")
    from .render import write_podcast_meta

    write_podcast_meta(wd, ir.documents, engine=tts.name, tone=parsed.tone, voices=voices, chapters=chapters)
    console.print(f"[green]✓[/] {audio}  ({int(seconds // 60)}:{int(seconds % 60):02d} min)")
    console.print(f"[green]✓[/] {wd / 'podcast.md'}  (transcript)")

    # Re-render the review page so it carries the player.
    insights = wd / "insights.json"
    if insights.is_file():
        try:
            ir, _ = apply_insights(ir, parse_insights(insights.read_text(encoding="utf-8")), "agent")
        except (ValidationError, ValueError):
            ir = heuristic_insights(ir)
    else:
        ir = heuristic_insights(ir)
    ir = _with_changes(ir, spec, adapter=adapter)
    page = write_html(ir, wd / "review.html", parsed.language, style)  # the page speaks the episode's language
    console.print(f"[green]✓[/] {page}  (review page with player)")
    if open_browser:
        webbrowser.open(page.resolve().as_uri())


@podcast_app.command("tones")
def podcast_tones() -> None:
    """List tone presets. Any other text passed to --tone is used as a custom tone."""
    from .podcast import DEFAULT_TONE, TONES

    for t in TONES.values():
        default = " [dim](default)[/]" if t.id == DEFAULT_TONE else ""
        console.print(f"• [bold]{t.id}[/]{default}  {t.summary}")
    console.print('\nOr describe your own: unboring podcast prompt <folder> --tone "two pirates arguing over a treasure map"')


def _voice_report(lang: str) -> dict:
    """Print what can speak on this machine and how to enable the rest. Returns the state."""
    import platform

    from .tts import ENGINES, EngineUnavailable, KokoroEngine, os_name, system_engine_name

    console.print(f"Voices on [bold]{os_name()}[/] ({platform.machine()}), Python {platform.python_version()}, language '{escape(lang)}'\n")
    state = {}
    for tier, engine in (("system", ENGINES[system_engine_name()]()), ("kokoro", KokoroEngine())):
        label = f"{tier} ({engine.name})" if tier == "system" else tier
        try:
            engine.check()
            v = engine.voices(lang)
            console.print(f"  [green]✓[/] [bold]{label}[/]  ready · {escape(v['guide'])} and {escape(v['skeptic'])}  [dim]{engine.description}[/]")
            state[tier] = "ready"
        except EngineUnavailable as e:
            console.print(f"  [yellow]✗[/] [bold]{label}[/]  {escape(e.reason)}  [dim]{engine.description}[/]")
            if e.fix:
                console.print(f"      → {escape(e.fix)}")
            state[tier] = e
    return state


@podcast_app.command("setup")
def podcast_setup(
    lang: str = typer.Option("es", "--lang", help="Language you will use, to check voices for it."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Download the Kokoro model without asking."),
) -> None:
    """Guided setup: shows which voices work here, how to enable the rest, and downloads Kokoro's model."""
    from .tts import KOKORO_FILES, KOKORO_RELEASE, KokoroEngine, download_kokoro, kokoro_dir

    state = _voice_report(lang)
    kokoro = KokoroEngine()
    if state["kokoro"] == "ready":
        console.print("\n[green]All set.[/] Podcasts use Kokoro by default (--engine auto).")
        return
    if not kokoro.package_installed():
        tip = "Meanwhile, podcasts use the system voices." if state["system"] == "ready" else ""
        console.print(f"\nOptional: run the command above for natural voices, then `unboring podcast setup` again. {tip}")
        return

    files = "\n".join(f"  {name} ({size} MB)" for name, size in KOKORO_FILES.values())
    console.print(f"\nKokoro is installed; its model is not. From {KOKORO_RELEASE}\n{files}\nTo   {kokoro_dir()}")
    if not yes and not typer.confirm("Download now?", default=True):
        raise typer.Exit(1)
    with console.status("Downloading...") as status:

        def hook(blocks, size, total):
            if total > 0:
                status.update(f"Downloading... {min(100, blocks * size * 100 // total)}%")

        for f in download_kokoro(hook):
            console.print(f"[green]✓[/] {f}")
    console.print("[green]All set.[/] Podcasts use Kokoro by default (--engine auto).")


@podcast_app.command("engines")
def podcast_engines(lang: str = typer.Option("es", "--lang", help="Language to check voices for.")) -> None:
    """Show which voice engines work on this machine and how to enable the others (downloads nothing)."""
    _voice_report(lang)


# --- info ------------------------------------------------------------------------


# --- theme -----------------------------------------------------------------------

theme_app = typer.Typer(help="Custom styles for the review page: unboring.css in your project.", no_args_is_help=True)
app.add_typer(theme_app, name="theme")


@theme_app.command("init")
def theme_init(
    path: Path = typer.Argument(Path("unboring.css"), help="Where to write it. Default: unboring.css here."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a starter unboring.css with every token, commented out at its default value."""
    from .theme import starter

    if path.exists() and not force:
        console.print(f"[yellow]{escape(str(path))} already exists.[/] Use --force to overwrite it.")
        raise typer.Exit(1)
    path.write_text(starter(), encoding="utf-8")
    console.print(f"[green]✓[/] {escape(str(path))}  Uncomment what you want to change; the next review uses it.")


@theme_app.command("check")
def theme_check(path: Optional[Path] = typer.Argument(None, help="Default: the unboring.css that review would use.")) -> None:
    """Check a theme: safe to inline, and readable (WCAG AA contrast)."""
    style = _theme(path)
    if style is None:
        console.print("No unboring.css found here or in a parent folder. Create one with `unboring theme init`.")
        raise typer.Exit(1)
    if not style.warnings:
        console.print("[green]✓[/] Safe to inline, and every text colour meets AA contrast.")


@app.command()
def adapters() -> None:
    """List supported SDD frameworks and the version each adapter is tested with."""
    for a in ADAPTERS:
        console.print(f"• [bold]{a.name}[/]  {a.tested_with}")


@app.command()
def agents() -> None:
    """List coding agents `init --ai` can install into."""
    for i in INTEGRATIONS.values():
        where = escape(i.target.format(skill="<skill>", short="<skill>"))
        console.print(f"• [bold]{i.key}[/]  {i.label} → {where}  [dim]{i.status}[/]")


@app.command()
def schema(
    which: str = typer.Argument("insights", help="insights (review analysis) or podcast (episode script)."),
) -> None:
    """Print a contract's JSON Schema: what agents must return."""
    from .podcast import podcast_json_schema

    schemas = {"insights": json_schema, "podcast": podcast_json_schema}
    if which not in schemas:
        console.print(f"[red]Unknown schema '{escape(which)}'.[/] Available: {', '.join(schemas)}")
        raise typer.Exit(2)
    # Plain print: the output is meant to be piped to a file or another tool.
    print(json.dumps(schemas[which](), indent=2, ensure_ascii=False))


@app.command()
def version() -> None:
    """Show the version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
