"""Adapter contract. One adapter per SDD framework (spec-kit, Kiro, OpenSpec, BMAD...).

An adapter only does the deterministic part: find the documents and pull out
whatever structure the framework guarantees (stories, requirements, tasks, markers).
Interpretation (summaries, decisions, risks) is the LLM layer's job.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..ir import OpenQuestion, SourceRef, SpecIR

CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION:?\s*([^\]]+)\]", re.IGNORECASE)


class Adapter(ABC):
    name: str = "base"

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
