"""Turn a saved review into the framework's own apply steps (#32).

unboringspec reviews; the framework changes the spec. Each adapter declares its steps
(spec-kit: /speckit.clarify, /speckit.plan, /speckit.tasks; OpenSpec: /opsx:update). This
module routes each review point to the step that owns its file, writes the text to pass to
each command, and finds where the command is installed and how this agent invokes it.
"""

from __future__ import annotations

import fnmatch
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .adapters.base import Adapter, ApplyStep
from .feedback import ReviewItem, SavedReview
from .ir import SpecIR


@dataclass
class PlannedStep:
    step: ApplyStep
    invocation: str | None  # how to call it here, e.g. /speckit-clarify; None = edit the documents
    installed: list[str] = field(default_factory=list)  # where it was found
    items: list[ReviewItem] = field(default_factory=list)
    input_file: Path | None = None


def _file_of(item: ReviewItem) -> str:
    return item.cite.rsplit(":", 1)[0] if item.cite else ""


def _owns(step: ApplyStep, item: ReviewItem) -> bool:
    f = _file_of(item)
    return any(p == "*" or fnmatch.fnmatch(f, p) for p in step.files)


def invocation_for(installed_path: str, command: str | None) -> str | None:
    """'.claude/skills/speckit-clarify/SKILL.md' -> '/speckit-clarify'; '.claude/commands/opsx/update.md' ->
    '/opsx:update'. Arguments of the canonical command (e.g. the OpenSpec change id) are kept."""
    if command is None:
        return None
    args = command.split(" ", 1)[1] if " " in command else ""
    parts = Path(installed_path).parts
    if "skills" in parts:
        name = "/" + parts[parts.index("skills") + 1]
    else:
        stem = Path(installed_path).name
        for suffix in (".prompt.md", ".md", ".toml"):
            stem = stem.removesuffix(suffix)
        name = f"/opsx:{stem}" if "opsx" in parts else "/" + stem
    return f"{name} {args}".strip()


def find_installed(step: ApplyStep, roots: list[Path]) -> list[str]:
    found = []
    for template in step.install_paths:
        for name in step.names or [""]:
            rel = template.format(name=name)
            for root in roots:
                if (root / rel).is_file():
                    found.append(str(root / rel))
    return list(dict.fromkeys(found))


def _slice(ir: SpecIR, step: ApplyStep, items: list[ReviewItem], approved: list[ReviewItem]) -> str:
    lines = [
        f"Review feedback from unboringspec for '{ir.feature}' ({ir.folder or 'this spec'}).",
        "These points are already decided by the reviewer: apply them and do not ask them again. "
        "Ask only about anything that is still ambiguous.",
        "",
    ]
    answers = [i for i in items if i.kind == "answer"]
    notes = [i for i in items if i.kind == "question"]
    if answers:
        lines.append("Answers to open questions:")
        lines += [f"- Q: {i.text} ({i.cite}) → A: {i.answer}" for i in answers]
        lines.append("")
    if notes:
        lines.append("Decisions the reviewer questioned:")
        for i in notes:
            lines.append(f"- {i.text} ({i.cite}): {i.choice}")
            lines.append(f"  Reviewer: {i.note or '(no comment)'}")
        lines.append("")
    if approved and "*" in step.files:
        lines.append("Approved by the reviewer (leave as is):")
        lines += [f"- {i.text} ({i.cite})" for i in approved]
        lines.append("")
    return "\n".join(lines)


def plan_apply(review: SavedReview, ir: SpecIR, adapter: Adapter, spec: Path, workdir: Path) -> list[PlannedStep]:
    """Route the review's points to the framework's steps and write each step's input file."""
    roots = [adapter.project_root(spec, adapter.project_markers()), Path.home()]
    actionable = [i for i in review.items if i.kind in ("answer", "question")]
    approved = [i for i in review.items if i.kind == "approve"]

    out_dir = workdir / "apply"
    shutil.rmtree(out_dir, ignore_errors=True)
    planned: list[PlannedStep] = []
    taken: set[int] = set()
    steps = adapter.apply_steps(ir)
    for step in steps:
        mine = [i for n, i in enumerate(actionable) if n not in taken and _owns(step, i)]
        taken.update(n for n, i in enumerate(actionable) if i in mine)
        planned.append(PlannedStep(step=step, invocation=step.command, items=mine))
    # Points whose file no step owns go to the first step that takes input.
    leftovers = [i for n, i in enumerate(actionable) if n not in taken]
    first_input = next((p for p in planned if p.step.files), None)
    if leftovers and first_input:
        first_input.items += leftovers

    anything = any(p.items for p in planned)
    kept: list[PlannedStep] = []
    for p in planned:
        takes_input = bool(p.step.files)
        if takes_input and not p.items:
            continue  # nothing for this command
        if not takes_input and not anything:
            continue  # regenerate / check only after something was applied
        if p.step.command is not None:
            p.installed = find_installed(p.step, roots)
            if p.installed:
                p.invocation = invocation_for(p.installed[0], p.step.command)
        if p.items:
            out_dir.mkdir(parents=True, exist_ok=True)
            p.input_file = out_dir / f"{len(kept) + 1}-{p.step.id}.md"
            p.input_file.write_text(_slice(ir, p.step, p.items, approved), encoding="utf-8")
        kept.append(p)
    return kept


def apply_hint(adapter: Adapter, ir: SpecIR, lang: str = "en") -> str:
    """One line for exported reviews, so an agent without the skill still uses the right commands."""
    from .i18n import table

    commands = [s.command for s in adapter.apply_steps(ir) if s.command and not s.optional]
    if not commands:
        return ""
    return table(lang)["apply_hint"].format(framework=adapter.label or adapter.name, commands=", ".join(commands))
