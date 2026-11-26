"""Adapter for GitHub spec-kit feature folders (specs/NNN-feature/).

Understands: spec.md, plan.md, tasks.md, research.md, data-model.md, quickstart.md, contracts/.
Parsing rules follow the templates in https://github.com/github/spec-kit/tree/main/templates.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ir import Attention, Decision, OpenQuestion, Requirement, SpecIR, Task, UserStory
from .base import (
    CLARIFICATION_RE,
    Adapter,
    ApplyStep,
    data_model_entities,
    find_clarifications,
    key_entities,
    merge_entities,
    read_documents,
    ref,
)

# The template's headings and labels, in English and in Spanish (specs written in Spanish, #44).
STORY_RE = re.compile(
    r"^#{2,4}\s+(?:User Story|Historia de usuario)\s+(\d+)\s*[-–—:]\s*(.+?)"
    r"(?:\s*\((?:Priority|Prioridad):\s*(P\d+)\))?\s*$",
    re.IGNORECASE,
)
REQ_RE = re.compile(r"^\s*[-*]\s+\*\*((?:FR|NFR|SC|RF|RNF|CE)-\d+)\*\*:?\s*(.+)$")
TASK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(T\d+)\s+(.*)$")
INPUT_RE = re.compile(
    r'^\*\*(?:Input|Entrada)\*\*:\s*(?:User description:\s*|Descripción del usuario:\s*)?"?(.+?)"?\s*$', re.IGNORECASE
)
TITLE_RE = re.compile(
    r"^#\s+(?:Feature Specification:\s*|Especificación(?: de(?: la)? (?:funcionalidad|característica))?:\s*)?(.+)$",
    re.IGNORECASE,
)
TECH_RE = re.compile(
    r"^\*\*(Language/Version|Primary Dependencies|Storage|Testing|Target Platform|Project Type|"
    r"Performance Goals|Constraints|Scale/Scope|"
    r"Lenguaje/Versión|Dependencias principales|Almacenamiento|Pruebas|Plataforma objetivo|Tipo de proyecto|"
    r"Objetivos de rendimiento|Restricciones|Escala/Alcance)\*\*:\s*(.+)$"
)
# Where spec-kit installs its commands for each agent ({name} = speckit-<cmd> or speckit.<cmd>).
SPECKIT_INSTALL_PATHS = [
    ".claude/skills/{name}/SKILL.md", ".claude/commands/{name}.md",
    ".github/skills/{name}/SKILL.md", ".github/prompts/{name}.prompt.md",
    ".agents/skills/{name}/SKILL.md", ".codex/prompts/{name}.md",
    ".cursor/skills/{name}/SKILL.md", ".cursor/commands/{name}.md",
    ".gemini/commands/{name}.toml",
]


def _speckit_step(cmd: str, covers: str, files: list[str], optional: bool = False) -> ApplyStep:
    return ApplyStep(
        id=cmd, command=f"/speckit.{cmd}", covers=covers, files=files, optional=optional,
        install_paths=SPECKIT_INSTALL_PATHS, names=[f"speckit-{cmd}", f"speckit.{cmd}"],
    )


# Reading order a reviewer expects: the what before the how.
DOC_ORDER = ("spec.md", "plan.md", "research.md", "data-model.md", "quickstart.md", "tasks.md")
FIELD_RE = re.compile(
    r"^\s*[-*]?\s*\*\*(Decision|Decisión|Rationale|Justificación|Motivo|Alternatives(?: considered)?|"
    r"Alternativas(?: consideradas)?)\*\*:?\s*(.*)$",
    re.IGNORECASE,
)
FIELD_KEYS = {"decision": "decision", "decisión": "decision", "rationale": "rationale", "justificación": "rationale",
              "motivo": "rationale"}


class SpecKitAdapter(Adapter):
    name = "spec-kit"
    tested_with = "spec-kit v1.4.4 templates"
    docs_url = "https://github.com/github/spec-kit"

    @classmethod
    def detect(cls, path: Path) -> bool:
        if not (path / "spec.md").is_file():
            return False
        has_siblings = any((path / f).is_file() for f in ("plan.md", "tasks.md", "research.md"))
        return has_siblings or path.parent.name == "specs"

    def project_markers(self) -> tuple[str, ...]:
        return (".specify", ".git")

    def apply_steps(self, ir: SpecIR) -> list:
        """spec-kit records answers with /speckit.clarify (spec.md only), revises the plan with
        /speckit.plan and regenerates tasks with /speckit.tasks. Checked against v1.4.4."""
        return [
            _speckit_step("clarify", "answers and decisions about the spec, recorded under ## Clarifications", ["spec.md"]),
            _speckit_step("plan", "decisions in the plan and research", ["plan.md", "research.md", "data-model.md", "quickstart.md", "contracts/*"]),
            _speckit_step("tasks", "regenerate the tasks from the updated spec and plan", []),
            _speckit_step("analyze", "check consistency across spec, plan and tasks", [], optional=True),
        ]

    def apply_checks(self, spec: Path) -> list[str]:
        """spec-kit commands act on the *active* feature: SPECIFY_FEATURE_DIRECTORY, else
        .specify/feature.json (written by /speckit-specify). Reviewing another feature and running
        /speckit-clarify would change the wrong spec, so say so before the steps."""
        import json
        import os

        root = self.project_root(spec, (".specify",))
        if not (root / ".specify").is_dir():
            return []
        try:
            rel = spec.resolve().relative_to(root).as_posix()
        except ValueError:
            return []
        how = (
            f'point it at this one first: write {{"feature_directory": "{rel}"}} to .specify/feature.json, '
            f"or run the commands with SPECIFY_FEATURE_DIRECTORY={rel}."
        )
        env = os.environ.get("SPECIFY_FEATURE_DIRECTORY")
        if env:
            current = env
        else:
            fj = root / ".specify" / "feature.json"
            try:
                current = json.loads(fj.read_text(encoding="utf-8")).get("feature_directory", "") if fj.is_file() else ""
            except (json.JSONDecodeError, OSError):
                current = ""
        if not current:
            return [f"spec-kit has no active feature, so its commands would not find this spec. Ask the user, then {how}"]
        resolved = (root / current).resolve() if not Path(current).is_absolute() else Path(current).resolve()
        if resolved != spec.resolve():
            return [
                f"spec-kit's active feature is {current}, not {rel}: its commands would change the wrong spec. "
                f"Ask the user, then {how}"
            ]
        return []

    def load(self, path: Path) -> SpecIR:
        docs = read_documents(path)
        rank = {n: i for i, n in enumerate(DOC_ORDER)}
        docs = dict(sorted(docs.items(), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0])))
        ir = SpecIR(feature=path.name, framework=self.name, documents=docs)

        spec = docs.get("spec.md", "")
        for line in spec.splitlines():
            if (m := TITLE_RE.match(line)) and ir.feature == path.name:
                ir.feature = m.group(1).strip()
            elif (m := INPUT_RE.match(line)) and not ir.description:
                ir.description = m.group(1).strip()
        ir.stories = self._stories(spec)
        ir.requirements = self._requirements(spec)
        ir.tasks = self._tasks(docs.get("tasks.md", ""))
        ir.entities = merge_entities(
            key_entities(docs.get("spec.md", ""), "spec.md"),
            data_model_entities(docs.get("data-model.md", ""), "data-model.md"),
        )
        ir.decisions = self._research_decisions(docs.get("research.md", "")) + self._tech_context(
            docs.get("plan.md", "")
        )
        ir.questions = find_clarifications(docs) + self._bare_markers(docs.get("plan.md", ""))
        for i, q in enumerate(ir.questions, start=1):
            q.id = f"Q{i}"
        ir.warnings = self._drift_warnings(ir)
        return ir

    def _drift_warnings(self, ir: SpecIR) -> list[str]:
        """Frameworks evolve. If a document exists but nothing parses, say so instead of
        silently rendering an empty review."""
        hint = f"The spec-kit template may have changed; this adapter is tested with {self.tested_with}."
        out = []
        if "spec.md" in ir.documents and not ir.stories and not ir.requirements:
            out.append(f"spec.md has no 'User Story N' headings or **FR-###** requirements. {hint}")
        if "tasks.md" in ir.documents and not ir.tasks:
            out.append(f"tasks.md has no '- [ ] T###' tasks. {hint}")
        return out

    # --- spec.md -----------------------------------------------------------------

    def _stories(self, text: str) -> list[UserStory]:
        lines = text.splitlines()
        stories: list[UserStory] = []
        for i, line in enumerate(lines):
            m = STORY_RE.match(line)
            if not m:
                continue
            summary = ""
            for nxt in lines[i + 1 :]:
                if nxt.startswith("#"):
                    break
                if nxt.strip():
                    summary = nxt.strip()
                    break
            stories.append(
                UserStory(
                    id=f"US{m.group(1)}",
                    title=m.group(2).strip(),
                    priority=m.group(3) or "",
                    summary=summary,
                    sources=[ref("spec.md", i + 1, line)],
                )
            )
        return stories

    def _requirements(self, text: str) -> list[Requirement]:
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            if m := REQ_RE.match(line):
                out.append(Requirement(id=m.group(1), text=m.group(2).strip(), sources=[ref("spec.md", i, line)]))
        return out

    # --- tasks.md ----------------------------------------------------------------

    def _tasks(self, text: str) -> list[Task]:
        out = []
        phase = ""
        for i, line in enumerate(text.splitlines(), start=1):
            if line.startswith("## "):
                phase = line[3:].strip()
                continue
            m = TASK_RE.match(line)
            if not m:
                continue
            body = m.group(3)
            story = re.search(r"\[(US\d+)\]", body)
            parallel = "[P]" in body
            clean = re.sub(r"\[(P|US\d+)\]\s*", "", body).strip()
            out.append(
                Task(
                    id=m.group(2),
                    text=clean,
                    story=story.group(1) if story else None,
                    parallel=parallel,
                    phase=phase,
                    done=m.group(1).lower() == "x",
                    sources=[ref("tasks.md", i, line)],
                )
            )
        return out

    # --- research.md / plan.md -------------------------------------------------------

    def _research_decisions(self, text: str) -> list[Decision]:
        decisions: list[Decision] = []
        current: dict | None = None
        heading, heading_line = "", 0

        def flush():
            if current and current.get("choice"):
                decisions.append(
                    Decision(
                        id=f"D{len(decisions) + 1}",
                        title=current.get("title") or current["choice"][:60],
                        choice=current["choice"],
                        rationale=current.get("rationale", ""),
                        alternatives=current.get("alternatives", []),
                        attention=Attention.review,
                        sources=current["sources"],
                    )
                )

        for i, line in enumerate(text.splitlines(), start=1):
            if line.startswith("#"):
                heading, heading_line = line.lstrip("#").strip(), i
                continue
            m = FIELD_RE.match(line)
            if not m:
                continue
            key, value = FIELD_KEYS.get(m.group(1).lower(), "alternatives"), m.group(2).strip()
            if key == "decision":
                flush()
                current = {"title": heading, "choice": value, "sources": [ref("research.md", i, line)]}
            elif current is None:
                continue
            elif key == "rationale":
                current["rationale"] = value
            else:
                current["alternatives"] = [a.strip() for a in re.split(r";|,\s(?=[A-Z])", value) if a.strip()]
        flush()
        return decisions

    def _bare_markers(self, text: str) -> list[OpenQuestion]:
        """plan.md's Technical Context uses a bare 'NEEDS CLARIFICATION' (no brackets)."""
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            m = TECH_RE.match(line)
            if m and "NEEDS CLARIFICATION" in m.group(2).upper() and not CLARIFICATION_RE.search(line):
                out.append(
                    OpenQuestion(
                        id="",
                        question=f"{m.group(1)} is not decided yet",
                        why_it_matters="The plan marks this technical choice as unresolved.",
                        sources=[ref("plan.md", i, line)],
                    )
                )
        return out

    def _tech_context(self, text: str) -> list[Decision]:
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            m = TECH_RE.match(line)
            if not m:
                continue
            value = m.group(2).strip()
            # Unresolved fields already surface as open questions; don't show them twice.
            if "NEEDS CLARIFICATION" in value.upper() or value.upper() in {"N/A", "NONE"}:
                continue
            out.append(
                Decision(
                    id=f"TC{len(out) + 1}",
                    title=m.group(1),
                    choice=value,
                    attention=Attention.routine,
                    sources=[ref("plan.md", i, line)],
                )
            )
        return out
