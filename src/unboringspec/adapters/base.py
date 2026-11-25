"""Adapter contract. One adapter per SDD framework (spec-kit, Kiro, OpenSpec, BMAD...).

An adapter only does the deterministic part: find the documents and pull out
whatever structure the framework guarantees (stories, requirements, tasks, markers).
Interpretation (summaries, decisions, risks) is the LLM layer's job.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..ir import Entity, OpenQuestion, SourceRef, SpecIR

CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION:?\s*([^\]]+)\]", re.IGNORECASE)


class Adapter(ABC):
    name: str = "base"
    # Which framework version the parsing rules were checked against. Frameworks evolve;
    # when the templates change, update the fixture under tests/fixtures/<adapter>/<version>/.
    tested_with: str = ""
    docs_url: str = ""

    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool:
        """Return True if this adapter understands the folder at `path`."""

    @abstractmethod
    def load(self, path: Path) -> SpecIR:
        """Read the folder and return a partially filled SpecIR."""


def read_documents(root: Path, patterns: tuple[str, ...] = ("*.md", "contracts/*")) -> dict[str, str]:
    docs: dict[str, str] = {}
    for pattern in patterns:
        for f in sorted(root.glob(pattern)):
            if f.is_file():
                docs[f.relative_to(root).as_posix()] = f.read_text(encoding="utf-8", errors="replace")
    return docs


def ref(file: str, lineno: int, line: str) -> SourceRef:
    return SourceRef(file=file, line=lineno, excerpt=line.strip()[:240])


def find_clarifications(docs: dict[str, str]) -> list[OpenQuestion]:
    out: list[OpenQuestion] = []
    for name, text in docs.items():
        for i, line in enumerate(text.splitlines(), start=1):
            for m in CLARIFICATION_RE.finditer(line):
                out.append(
                    OpenQuestion(
                        id=f"Q{len(out) + 1}",
                        question=m.group(1).strip(),
                        why_it_matters="The spec explicitly marks this as unresolved.",
                        sources=[ref(name, i, line)],
                    )
                )
    return out


# --- entities ----------------------------------------------------------------------

ENTITY_BULLET_RE = re.compile(r"^\s*[-*+]\s+\*\*(.+?)\*\*:?\s*(.*)$")
FIELD_BULLET_RE = re.compile(r"^\s*[-*+]\s+`?\*{0,2}([A-Za-z_][\w ]{0,40}?)\*{0,2}`?\s*(?::|—|–|\s-\s)")
TABLE_ROW_RE = re.compile(r"^\s*\|\s*`?([^|`]+?)`?\s*\|")
NOT_ENTITIES = {
    "entities", "key entities", "overview", "relationships", "relationship", "validation rules", "validation",
    "state transitions", "states", "data model", "notes", "constraints", "indexes", "fields", "attributes",
}


NOT_FIELDS = {"description", "purpose", "validation", "validation rules", "relationships", "state", "states", "notes", "rules"}


def _attributes(text: str) -> list[str]:
    """'name, owner, invite token, created at.' -> ['name', 'owner', 'invite token', 'created at']"""
    text = re.sub(r"\(.*?\)", "", text).strip().rstrip(".")
    parts = re.split(r",|;|\band\b", text)
    return [p.strip(" .`*") for p in parts if p.strip(" .`*") and len(p.strip()) <= 40]


def key_entities(text: str, file: str) -> list[Entity]:
    """spec-kit's '### Key Entities' list: '- **Album**: name, owner, created at.'"""
    out, inside = [], False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("#"):
            inside = "key entities" in line.lower()
            continue
        if inside and (m := ENTITY_BULLET_RE.match(line)):
            out.append(Entity(name=m.group(1).strip(), attributes=_attributes(m.group(2)), sources=[ref(file, i, line)]))
    return out


def data_model_entities(text: str, file: str) -> list[Entity]:
    """data-model.md: each '##'/'###' heading that names an entity, with fields from a table
    (first row is the header), field bullets ('- `name`: string') or '- **Fields**: a, b, c'."""
    out: list[Entity] = []
    current: Entity | None = None
    table_row = 0  # position inside the current Markdown table; 0 = not in a table
    for i, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^#{2,3}\s+(?:Entity:\s*)?`?([A-Z][\w ]{0,40}?)`?\s*$", line)
        if m:
            name = m.group(1).strip()
            current = None if name.lower() in NOT_ENTITIES else Entity(name=name, sources=[ref(file, i, line)])
            if current:
                out.append(current)
            table_row = 0
            continue
        if line.startswith("#"):
            current, table_row = None, 0
            continue
        row = TABLE_ROW_RE.match(line)
        table_row = table_row + 1 if row else 0
        if current is None:
            continue
        if row:
            cell = row.group(1).strip()
            if table_row > 1 and not set(cell) <= set("-: "):  # skip header row and separator
                current.attributes.append(cell)
            continue
        label = ENTITY_BULLET_RE.match(line)
        if label:
            key = label.group(1).strip()
            if key.lower() in {"fields", "attributes"}:
                current.attributes += _attributes(label.group(2))
            elif key.lower() not in NOT_FIELDS:
                current.attributes.append(key)  # '- **album**: Album reference'
            continue
        field = FIELD_BULLET_RE.match(line)
        if field:
            current.attributes.append(field.group(1).strip())
    return out


def merge_entities(*groups: list[Entity]) -> list[Entity]:
    """Same entity named in several documents: keep the first, add attributes it lacks."""
    merged: dict[str, Entity] = {}
    for group in groups:
        for e in group:
            key = e.name.lower()
            if key not in merged:
                merged[key] = e.model_copy(deep=True)
                continue
            known = {a.lower() for a in merged[key].attributes}
            merged[key].attributes += [a for a in e.attributes if a.lower() not in known]
            merged[key].sources += e.sources
    return list(merged.values())
