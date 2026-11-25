"""Install unboringspec into the coding agent the user already has.

Most agents now read Agent Skills (a folder with a SKILL.md); only the folder differs.
Folder conventions follow the ones spec-kit uses for each agent. Every agent gets the core
skills; optional ones (the podcast) only when the user asks for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str  # skill folder name and slash command, e.g. unboring-review
    short: str  # used where an agent wants a dotted command name, e.g. unboring.review
    description: str
    template: str  # file under templates/
    argument_hint: str = "[spec folder, e.g. specs/001-my-feature]"
    optional: bool = False  # installed only when asked for (init --podcast)


SKILLS: dict[str, Skill] = {
    s.name: s
    for s in [
        Skill(
            "unboring-review",
            "review",
            "Turn a Spec-Driven Development spec folder (spec-kit, Kiro, OpenSpec...) into a short, "
            "attention-ranked review page with traceable decisions, risks and open questions. Use when the "
            "user wants to review, digest or summarise a spec, plan or task list.",
            "skill.md",
        ),
        Skill(
            "unboring-podcast",
            "podcast",
            "Turn a Spec-Driven Development spec into a short two-host podcast episode (a guide and a skeptic) "
            "voiced locally, so the reviewer can listen instead of read. Use when the user asks for a podcast, "
            "audio summary or something to listen to about a spec.",
            "skill-podcast.md",
            "[spec folder] [language, e.g. es]",
            optional=True,
        ),
    ]
}

# Kept for backwards compatibility with code importing the old single-skill names.
SKILL_NAME = "unboring-review"
DESCRIPTION = SKILLS[SKILL_NAME].description


@dataclass(frozen=True)
class Integration:
    key: str
    label: str
    target: str  # path template relative to the project root: {skill} or {short}
    kind: str = "skill"  # "skill" (SKILL.md) or "gemini-toml"
    status: str = "experimental"  # "tested" once someone has run it end to end
    # Agent-specific frontmatter lines. Other agents ignore unknown fields, but we only
    # write what each agent documents.
    extra_frontmatter: tuple[str, ...] = ()

    def path_for(self, skill: Skill) -> str:
        return self.target.format(skill=skill.name, short=skill.short)


INTEGRATIONS: dict[str, Integration] = {
    i.key: i
    for i in [
        Integration(
            "claude",
            "Claude Code",
            ".claude/skills/{skill}/SKILL.md",
            status="tested",
            # Pre-approve only the unboring CLI while the skill runs; every other command
            # still asks. Writing JSON files follows the user's normal edit permissions.
            extra_frontmatter=("allowed-tools: Bash(unboring:*)",),
        ),
        Integration("copilot", "GitHub Copilot (VS Code)", ".github/skills/{skill}/SKILL.md"),
        Integration("codex", "OpenAI Codex", ".agents/skills/{skill}/SKILL.md"),
        Integration("cursor", "Cursor", ".cursor/skills/{skill}/SKILL.md"),
        Integration("gemini", "Gemini CLI", ".gemini/commands/unboring.{short}.toml", kind="gemini-toml"),
        Integration("agents", "Any agent reading .agents/skills", ".agents/skills/{skill}/SKILL.md"),
    ]
}


def skill_body(skill: Skill | str = SKILL_NAME) -> str:
    skill = SKILLS[skill] if isinstance(skill, str) else skill
    return files("unboringspec").joinpath(f"templates/{skill.template}").read_text(encoding="utf-8")


def render_integration(integ: Integration, skill: Skill | str = SKILL_NAME) -> str:
    skill = SKILLS[skill] if isinstance(skill, str) else skill
    body = skill_body(skill)
    if integ.kind == "gemini-toml":
        escaped = body.replace("\\", "\\\\").replace('"""', '\\"""')
        return (
            f'description = "{skill.description}"\n'
            f'prompt = """\n{escaped}\nArguments from the user: {{{{args}}}}\n"""\n'
        )
    return (
        "---\n"
        f"name: {skill.name}\n"
        f"description: {skill.description}\n"
        f'argument-hint: "{skill.argument_hint}"\n'
        + "".join(f"{line}\n" for line in integ.extra_frontmatter)
        + "---\n\n"
        + body
    )


def install(root: Path, keys: list[str], force: bool = False, podcast: bool = False) -> list[tuple[Path, str]]:
    """Write the skills for each chosen agent. Optional skills (the podcast) only when asked.
    Returns (path, outcome) pairs."""
    skills = [s for s in SKILLS.values() if not s.optional or podcast]
    results: list[tuple[Path, str]] = []
    written: set[Path] = set()
    for key in keys:
        integ = INTEGRATIONS[key]
        for skill in skills:
            path = root / integ.path_for(skill)
            if path in written:
                continue
            written.add(path)
            if path.exists() and not force:
                results.append((path, "exists (use --force to overwrite)"))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_integration(integ, skill), encoding="utf-8")
            results.append((path, "written"))

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".unboring/" not in current.splitlines():
        sep = "" if not current or current.endswith("\n") else "\n"
        gitignore.write_text(current + sep + "# unboringspec working files\n.unboring/\n", encoding="utf-8")
        results.append((gitignore, "added .unboring/"))
    return results
