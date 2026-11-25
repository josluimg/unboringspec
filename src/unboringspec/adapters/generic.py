"""Fallback adapter: any folder of Markdown files (Kiro, OpenSpec, BMAD, hand-written specs).

It extracts only clarification markers; the LLM layer does the rest.
"""

from __future__ import annotations

from pathlib import Path

from ..ir import SpecIR
from .base import Adapter, find_clarifications, read_documents


class GenericAdapter(Adapter):
    name = "generic"
    tested_with = "any Markdown; analysis relies on the LLM"

    @classmethod
    def detect(cls, path: Path) -> bool:
        return any(path.glob("*.md"))

    def load(self, path: Path) -> SpecIR:
        docs = read_documents(path, ("*.md", "**/*.md"))
        return SpecIR(feature=path.name, framework=self.name, documents=docs, questions=find_clarifications(docs))
