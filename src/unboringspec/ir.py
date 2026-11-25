"""Spec IR: the framework-agnostic model every adapter produces and every renderer consumes.

Every claim carries `sources` pointing back to a file and line, so a reviewer can
always verify a summary against the original spec.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    file: str
    line: int
    excerpt: str = ""

    @property
    def label(self) -> str:
        return f"{self.file}:{self.line}"


class Attention(str, Enum):
    """How much human judgment an item needs. This drives what the reviewer sees first."""

    decide = "decide"  # blocked on a human call (ambiguity, missing info, risky trade-off)
    review = "review"  # worth a look, a reasonable person could disagree
    routine = "routine"  # conventional choice, skim or skip


class Decision(BaseModel):
    id: str
    title: str
    choice: str
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)
    risk: str = ""
    attention: Attention = Attention.review
    sources: list[SourceRef] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    id: str
    question: str
    why_it_matters: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class Risk(BaseModel):
    id: str
    title: str
    impact: str = ""
    mitigation: str = ""
    severity: Literal["low", "medium", "high"] = "medium"
    sources: list[SourceRef] = Field(default_factory=list)


class Requirement(BaseModel):
    id: str
    text: str
    sources: list[SourceRef] = Field(default_factory=list)


class UserStory(BaseModel):
    id: str
    title: str
    priority: str = ""
    summary: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    text: str
    story: str | None = None
    parallel: bool = False
    done: bool = False
    sources: list[SourceRef] = Field(default_factory=list)


class Summary(BaseModel):
    one_liner: str
    bullets: list[str] = Field(default_factory=list)
    you_must_decide: list[str] = Field(default_factory=list)


class SpecIR(BaseModel):
    feature: str
    framework: str
    description: str = ""
    documents: dict[str, str] = Field(default_factory=dict)
    summary: Summary | None = None
    stories: list[UserStory] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    generated_by: str = "heuristic"

    def decisions_by_attention(self, level: Attention) -> list[Decision]:
        return [d for d in self.decisions if d.attention == level]
