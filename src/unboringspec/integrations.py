"""Install unboringspec into the coding agent the user already has.

Most agents now read Agent Skills (a folder with a SKILL.md); only the folder differs.
Folder conventions follow the ones spec-kit uses for each agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

SKILL_NAME = "unboring-review"
DESCRIPTION = (
    "Turn a Spec-Driven Development spec folder (spec-kit, Kiro, OpenSpec...) into a short, "
    "attention-ranked review page with traceable decisions, risks and open questions. Use when the "
    "user wants to review, digest or summarise a spec, plan or task list."
)
ARGUMENT_HINT = "[spec folder, e.g. specs/001-my-feature]"


@dataclass(frozen=True)
class Integration:
    key: str
    label: str
    target: str  # path relative to the project root
    kind: str = "skill"  # "skill" (SKILL.md) or "gemini-toml"
    status: str = "experimental"  # "tested" once someone has run it end to end
    # Agent-specific frontmatter lines. Other agents ignore unknown fields, but we only
    # write what each agent documents.
    extra_frontmatter: tuple[str, ...] = ()


INTEGRATIONS: dict[str, Integration] = {
    i.key: i
    for i in [
        Integration(
            "claude",
            "Claude Code",
            f".claude/skills/{SKILL_NAME}/SKILL.md",
            status="tested",
            # Pre-approve only the unboring CLI while the skill runs; every other command
            # still asks. Writing insights.json follows the user's normal edit permissions.
            extra_frontmatter=("allowed-tools: Bash(unboring:*)",),
        ),
        Integration("copilot", "GitHub Copilot (VS Code)", f".github/skills/{SKILL_NAME}/SKILL.md"),
        Integration("codex", "OpenAI Codex", f".agents/skills/{SKILL_NAME}/SKILL.md"),
        Integration("cursor", "Cursor", f".cursor/skills/{SKILL_NAME}/SKILL.md"),
        Integration("gemini", "Gemini CLI", ".gemini/commands/unboring.review.toml", kind="gemini-toml"),
        Integration("agents", "Any agent reading .agents/skills", f".agents/skills/{SKILL_NAME}/SKILL.md"),
    ]
}


def skill_body() -> str:
    return files("unboringspec").joinpath("templates/skill.md").read_text(encoding="utf-8")


def render_integration(integ: Integration) -> str:
    body = skill_body()
    if integ.kind == "gemini-toml":
        escaped = body.replace("\\", "\\\\").replace('"""', '\\"""')
        return (
            f'description = "{DESCRIPTION}"\n'
            f'prompt = """\n{escaped}\nArguments from the user: {{{{args}}}}\n"""\n'
        )
    return (
        "---\n"
        f"name: {SKILL_NAME}\n"
        f"description: {DESCRIPTION}\n"
        f'argument-hint: "{ARGUMENT_HINT}"\n'
        + "".join(f"{line}\n" for line in integ.extra_frontmatter)
        + "---\n\n"
        + body
    )


def install(root: Path, keys: list[str], force: bool = False) -> list[tuple[Path, str]]:
    """Write the integration files. Returns (path, outcome) pairs."""
    results: list[tuple[Path, str]] = []
    written: set[Path] = set()
    for key in keys:
        integ = INTEGRATIONS[key]
        path = root / integ.target
        if path in written:
            continue
        written.add(path)
        if path.exists() and not force:
            results.append((path, "exists (use --force to overwrite)"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_integration(integ), encoding="utf-8")
        results.append((path, "written"))

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".unboring/" not in current.splitlines():
        sep = "" if not current or current.endswith("\n") else "\n"
        gitignore.write_text(current + sep + "# unboringspec working files\n.unboring/\n", encoding="utf-8")
        results.append((gitignore, "added .unboring/"))
    return results
