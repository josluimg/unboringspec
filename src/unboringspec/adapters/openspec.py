"""Adapter for OpenSpec (https://github.com/Fission-AI/OpenSpec).

The unit of review is a change: openspec/changes/<change-id>/ (archived changes under
changes/archive/ work too) with proposal.md, design.md, tasks.md and spec deltas in
specs/<capability>/spec.md. A capability spec, openspec/specs/<capability>/, is also accepted.

Parsing follows the `spec-driven` schema templates of OpenSpec v2.2.0 and its delta parser
(ADDED / MODIFIED / REMOVED / RENAMED Requirements). Real changes often drift from the
templates (free-form design sections, unnumbered tasks), so the rules are deliberately lenient.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ir import Attention, Decision, OpenQuestion, Requirement, Risk, SpecIR, Task
from .base import Adapter, find_clarifications, read_documents, ref

DELTA_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.IGNORECASE)
REQ_HEADER_RE = re.compile(r"^###\s*Requirement:\s*(.+?)\s*#*\s*$", re.IGNORECASE)
REMOVED_BULLET_RE = re.compile(r"^\s*[-*+]\s*`?###\s*Requirement:\s*(.+?)`?\s*$", re.IGNORECASE)
RENAME_RE = re.compile(r"^\s*[-*+]?\s*(FROM|TO):\s*`?###\s*Requirement:\s*(.+?)`?\s*$", re.IGNORECASE)
REASON_RE = re.compile(r"^\s*[-*+]?\s*\*\*(Reason|Migration)\*\*:?\s*(.+)$", re.IGNORECASE)
TASK_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(?:(\d+(?:\.\d+)*)\.?\s+)?(.+)$")
H2_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$")
H3_RE = re.compile(r"^###\s+(.+?)\s*#*\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
BOLD_LEAD_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*(.*)$")
ARROW_RE = re.compile(r"\s*(?:→|->|—>)\s*")
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")

DOC_ORDER = ("proposal.md", "design.md")  # then specs/**, then tasks.md
# design.md sections that are context, not decisions.
NON_DECISION_SECTIONS = {
    "context", "goals / non-goals", "goals/non-goals", "goals", "non-goals", "risks / trade-offs",
    "risks/trade-offs", "risks", "trade-offs", "open questions", "migration plan", "migration",
}


def _norm(heading: str) -> str:
    return heading.strip().lower()


def _sections(text: str) -> list[tuple[str, int, list[tuple[int, str]]]]:
    """Split Markdown into level-2 sections: (title, header line, [(line number, line)])."""
    out: list[tuple[str, int, list[tuple[int, str]]]] = []
    current: tuple[str, int, list[tuple[int, str]]] | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        m = H2_RE.match(line)
        if m and not line.startswith("###"):
            current = (m.group(1), i, [])
            out.append(current)
        elif current is not None:
            current[2].append((i, line))
    return out


def _first_paragraph(lines: list[tuple[int, str]]) -> tuple[int, str]:
    """First prose paragraph, skipping comments, headings and blank lines."""
    start, buf = 0, []
    for i, line in lines:
        s = line.strip()
        if not s or s.startswith("<!--"):
            if buf:
                break
            continue
        if s.startswith("#"):
            if buf:
                break
            continue
        start = start or i
        buf.append(s)
    return start, " ".join(buf)


def _first_sentence(text: str, limit: int = 240) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = m.group(1) if m else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _pretty(change_id: str) -> str:
    words = DATE_PREFIX_RE.sub("", change_id).replace("_", "-").split("-")
    return " ".join(words).strip().capitalize() or change_id


class OpenSpecAdapter(Adapter):
    name = "openspec"
    tested_with = "OpenSpec v2.2.0, spec-driven schema"
    docs_url = "https://github.com/Fission-AI/OpenSpec"

    @classmethod
    def detect(cls, path: Path) -> bool:
        # A change folder.
        if (path / "proposal.md").is_file() and (
            (path / "specs").is_dir()
            or (path / "tasks.md").is_file()
            or (path / "design.md").is_file()
            or (path / ".openspec.yaml").is_file()
            or path.parent.name in {"changes", "archive"}
        ):
            return True
        # A capability spec: openspec/specs/<capability>/spec.md (capabilities can be nested).
        return (path / "spec.md").is_file() and "openspec" in path.parts[:-1] and "specs" in path.parts[:-1]

    def load(self, path: Path) -> SpecIR:
        docs = read_documents(path, ("*.md", "specs/**/*.md"))
        docs = dict(sorted(docs.items(), key=lambda kv: self._rank(kv[0])))
        # A change is titled by its proposal; a capability spec by its own heading and Purpose.
        lead = docs.get("proposal.md") or docs.get("spec.md", "")
        ir = SpecIR(feature=self._title(path, lead), framework=self.name, documents=docs)
        ir.description = self._why(lead)

        for name, text in docs.items():
            if name == "spec.md" or (name.startswith("specs/") and name.endswith(".md")):
                ir.requirements += self._requirements(name, text, len(ir.requirements))
        ir.tasks = self._tasks(docs.get("tasks.md", ""))
        ir.decisions = self._breaking(docs.get("proposal.md", "")) + self._design_decisions(docs.get("design.md", ""))
        ir.risks = self._risks(docs.get("design.md", ""))
        ir.questions = find_clarifications(docs) + self._open_questions(docs.get("design.md", ""))
        for i, q in enumerate(ir.questions, start=1):
            q.id = f"Q{i}"
        ir.warnings = self._drift_warnings(path, ir)
        return ir

    # --- documents ---------------------------------------------------------------

    @staticmethod
    def _rank(name: str) -> tuple[int, str]:
        if name in DOC_ORDER:
            return DOC_ORDER.index(name), name
        if name == "spec.md" or name.startswith("specs/"):
            return len(DOC_ORDER), name
        if name == "tasks.md":
            return len(DOC_ORDER) + 2, name
        return len(DOC_ORDER) + 1, name

    @staticmethod
    def _title(path: Path, proposal: str) -> str:
        for line in proposal.splitlines():
            if line.startswith("# "):
                title = re.sub(r"^(Change|Proposal)\s*:\s*", "", line[2:].strip(), flags=re.IGNORECASE)
                title = re.sub(r"\s+Specification$", "", title, flags=re.IGNORECASE)
                if title and _norm(title) not in {"proposal", "change", "spec delta"}:
                    return title[:1].upper() + title[1:]
                break
        return _pretty(path.name)

    @staticmethod
    def _why(proposal: str) -> str:
        for title, _, lines in _sections(proposal):
            if _norm(title) in {"why", "purpose"}:
                return _first_paragraph(lines)[1]
        return ""

    # --- spec deltas ---------------------------------------------------------------

    def _requirements(self, file: str, text: str, offset: int) -> list[Requirement]:
        lines = text.splitlines()
        out: list[Requirement] = []
        capability = file.removeprefix("specs/").removesuffix("/spec.md") if file != "spec.md" else ""
        op = ""  # "" means a capability spec, not a delta
        pending_from: tuple[int, str] | None = None

        def add(change: str, name: str, lineno: int, statement: str = "") -> None:
            where = f" ({capability})" if capability else ""
            text_ = f"{name}{where}" + (f": {statement}" if statement else "")
            out.append(
                Requirement(id=f"R{offset + len(out) + 1}", text=text_, change=change, sources=[ref(file, lineno, lines[lineno - 1])])
            )

        for idx, line in enumerate(lines):
            lineno = idx + 1
            if line.startswith("## "):
                m = DELTA_RE.match(line)
                op = m.group(1).lower() if m else ""
                continue
            if op == "renamed":
                m = RENAME_RE.match(line)
                if m and m.group(1).upper() == "FROM":
                    pending_from = (lineno, m.group(2))
                elif m and pending_from:
                    add("renamed", f"{pending_from[1]} → {m.group(2)}", pending_from[0])
                    pending_from = None
                continue
            header = REQ_HEADER_RE.match(line) or (REMOVED_BULLET_RE.match(line) if op == "removed" else None)
            if not header:
                continue
            name = header.group(1).strip("` ")
            add(op, name, lineno, self._statement(lines, idx + 1, removed=op == "removed"))
        return out

    @staticmethod
    def _statement(lines: list[str], start: int, removed: bool) -> str:
        """The requirement's first sentence, or for a removal its Reason (and Migration)."""
        notes = []
        for line in lines[start:]:
            s = line.strip()
            if s.startswith("#") or REMOVED_BULLET_RE.match(line):
                break
            if removed:
                m = REASON_RE.match(line)
                if m:
                    notes.append(f"{m.group(1).capitalize()}: {m.group(2).strip()}")
                continue
            if s and not s.startswith("<!--") and not s.startswith(("-", "*")):
                return _first_sentence(s)
        return " · ".join(notes)

    # --- tasks -----------------------------------------------------------------------

    @staticmethod
    def _tasks(text: str) -> list[Task]:
        out: list[Task] = []
        group = None
        for i, line in enumerate(text.splitlines(), start=1):
            m = H2_RE.match(line)
            if m and not line.startswith("###"):
                group = re.sub(r"^\d+(\.\d+)*\.?\s*", "", m.group(1)).strip() or None
                continue
            m = TASK_RE.match(line)
            if not m:
                continue
            out.append(
                Task(
                    id=m.group(2) or f"T{len(out) + 1}",
                    text=m.group(3).strip(),
                    story=group,
                    phase=group or "",
                    done=m.group(1).lower() == "x",
                    sources=[ref("tasks.md", i, line)],
                )
            )
        return out

    # --- design.md and proposal.md ---------------------------------------------------

    @staticmethod
    def _breaking(proposal: str) -> list[Decision]:
        out = []
        for i, line in enumerate(proposal.splitlines(), start=1):
            if "BREAKING" in line:
                clean = re.sub(r"\*\*BREAKING\*\*:?|BREAKING:?", "", line).strip(" -*+:")
                clean = clean[:1].upper() + clean[1:]
                out.append(
                    Decision(
                        id=f"B{len(out) + 1}",
                        title="Breaking change",
                        choice=clean or line.strip(),
                        risk="Existing users or integrations break unless they migrate.",
                        attention=Attention.decide,
                        sources=[ref("proposal.md", i, line)],
                    )
                )
        return out

    def _design_decisions(self, design: str) -> list[Decision]:
        decisions: list[Decision] = []
        sections = _sections(design)

        def add(title: str, body: str, lineno: int, line: str) -> None:
            lead = BOLD_LEAD_RE.match(body)
            if lead and not title:
                title, body = lead.group(1), lead.group(2)
            if not body and not title:
                return
            decisions.append(
                Decision(
                    id=f"D{len(decisions) + 1}",
                    title=(title or _first_sentence(body, 60)).strip(),
                    choice=_first_sentence(body) if body else title,
                    attention=Attention.review,
                    sources=[ref("design.md", lineno, line)],
                )
            )

        explicit = [s for s in sections if _norm(s[0]) == "decisions"]
        if explicit:
            _, _, lines = explicit[0]
            sub = [(i, H3_RE.match(l).group(1)) for i, l in lines if H3_RE.match(l)]
            if sub:  # ### Decision title, then a paragraph
                for n, (i, title) in enumerate(sub):
                    end = sub[n + 1][0] if n + 1 < len(sub) else float("inf")
                    body = [(j, l) for j, l in lines if i < j < end]
                    start, para = _first_paragraph(body)
                    add(re.sub(r"^Decision\s*:\s*", "", title, flags=re.IGNORECASE), para, i, design.splitlines()[i - 1])
            else:  # - **Decision**: why, or plain bullets
                for i, line in lines:
                    m = BULLET_RE.match(line)
                    if m and not line.startswith(("  ", "\t")):
                        add("", re.sub(r"^Decision\s*:\s*", "", m.group(1), flags=re.IGNORECASE), i, line)
            return decisions

        # Free-form design: every section that is not context is a decision.
        for title, lineno, lines in sections:
            if _norm(title) in NON_DECISION_SECTIONS:
                continue
            _, para = _first_paragraph(lines)
            add(title, para, lineno, design.splitlines()[lineno - 1])
        return decisions

    @staticmethod
    def _bullets(design: str, wanted: set[str]) -> list[tuple[int, str, str]]:
        out = []
        for title, _, lines in _sections(design):
            if _norm(title) in wanted:
                for i, line in lines:
                    m = BULLET_RE.match(line)
                    if m and not line.startswith(("  ", "\t")):
                        out.append((i, line, m.group(1).strip()))
        return out

    def _risks(self, design: str) -> list[Risk]:
        out = []
        for i, line, text in self._bullets(design, {"risks / trade-offs", "risks/trade-offs", "risks", "trade-offs"}):
            text = re.sub(r"^\[(?:Risk|Trade-?off)\]\s*", "", text, flags=re.IGNORECASE)
            parts = ARROW_RE.split(text, maxsplit=1)
            if len(parts) == 1 and "Mitigation:" in text:
                parts = [p.strip() for p in text.split("Mitigation:", 1)]
            title = parts[0].strip()
            mitigation = re.sub(r"^Mitigation:\s*", "", parts[1].strip(), flags=re.IGNORECASE) if len(parts) > 1 else ""
            out.append(Risk(id=f"R{len(out) + 1}", title=title, mitigation=mitigation, sources=[ref("design.md", i, line)]))
        return out

    def _open_questions(self, design: str) -> list[OpenQuestion]:
        return [
            OpenQuestion(
                id="",
                question=text,
                why_it_matters="The design lists this as an open question.",
                sources=[ref("design.md", i, line)],
            )
            for i, line, text in self._bullets(design, {"open questions"})
        ]

    # --- drift -----------------------------------------------------------------------

    def _drift_warnings(self, path: Path, ir: SpecIR) -> list[str]:
        hint = f"The OpenSpec format may have changed; this adapter is tested with {self.tested_with}."
        out = []
        proposal = ir.documents.get("proposal.md")
        if proposal is not None and not any(_norm(t) in {"why", "what changes"} for t, _, _ in _sections(proposal)):
            out.append(f"proposal.md has no '## Why' or '## What Changes' section. {hint}")
        deltas = [n for n in ir.documents if n.startswith("specs/")]
        if deltas and not ir.requirements:
            out.append(f"{', '.join(deltas)} contain no '### Requirement:' headers or RENAMED pairs. {hint}")
        if "proposal.md" in ir.documents and not deltas:
            meta = path / ".openspec.yaml"
            skip = meta.is_file() and re.search(r"^\s*skip_specs:\s*true\b", meta.read_text(encoding="utf-8"), re.M)
            if not skip:
                out.append("This change has no spec deltas under specs/, so no requirement changes are shown.")
        if "tasks.md" in ir.documents and not ir.tasks:
            out.append(f"tasks.md has no '- [ ]' tasks. {hint}")
        return out
