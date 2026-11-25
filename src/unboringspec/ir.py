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
    # For frameworks that describe changes as deltas (OpenSpec): added, modified, removed, renamed.
    change: str = ""
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
    phase: str = ""  # the tasks.md heading the task sits under, e.g. "Phase 1: Setup"
    parallel: bool = False
    done: bool = False
    sources: list[SourceRef] = Field(default_factory=list)


class Entity(BaseModel):
    """A domain entity, e.g. from spec-kit's Key Entities or data-model.md."""

    name: str
    attributes: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class Diagram(BaseModel):
    """A Mermaid diagram shown on the review page."""

    id: str
    kind: str  # tasks, data-model, journey, sequence, flow, state
    title: str
    mermaid: str
    origin: str = "spec"  # "spec" (built from the documents, no LLM) or "agent"
    sources: list[SourceRef] = Field(default_factory=list)


class ChangeItem(BaseModel):
    """One semantic difference between two versions of a spec."""

    area: str  # requirement, story, task, decision, question, risk, entity
    change: str  # added, removed, changed, resolved, completed, reopened
    label: str
    before: str = ""
    after: str = ""
    sources: list[SourceRef] = Field(default_factory=list)  # in the current version
    was_at: str = ""  # file:line in the previous version, for removed items


class FileDelta(BaseModel):
    file: str
    added: int = 0
    removed: int = 0
    status: str = "modified"  # added, removed, modified


class ChangeSet(BaseModel):
    baseline: str  # human description of what we compare with
    items: list[ChangeItem] = Field(default_factory=list)
    files: list[FileDelta] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FollowUpItem(BaseModel):
    """What happened to one point of the reader's last review in the current version."""

    kind: str  # answer, question, approve (what the reader did)
    outcome: str  # addressed, pending, changed, not-addressed, approved, approved-changed, removed
    label: str
    reader_said: str = ""  # the answer or the note
    key: str = ""  # current item key, when the item still exists
    sources: list[SourceRef] = Field(default_factory=list)


class FollowUp(BaseModel):
    reviewed: str  # when / which version was reviewed
    same_version: bool = False
    items: list[FollowUpItem] = Field(default_factory=list)
    carried: dict[str, dict] = Field(default_factory=dict)  # key -> mark to pre-fill on the page
    flags: dict[str, str] = Field(default_factory=dict)  # key -> message shown on the card
    notes: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    one_liner: str
    bullets: list[str] = Field(default_factory=list)
    you_must_decide: list[str] = Field(default_factory=list)


class SpecIR(BaseModel):
    feature: str
    framework: str
    folder: str = ""  # the spec folder's name, e.g. 001-photo-albums or add-2fa
    description: str = ""
    documents: dict[str, str] = Field(default_factory=dict)
    summary: Summary | None = None
    stories: list[UserStory] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    diagrams: list[Diagram] = Field(default_factory=list)  # from the agent; spec diagrams are built at render time
    generated_by: str = "heuristic"
    warnings: list[str] = Field(default_factory=list)
    changes: ChangeSet | None = None  # what changed since the previous version, set at render time
    follow_up: FollowUp | None = None  # what happened to the reader's last review, set at render time

    def decisions_by_attention(self, level: Attention) -> list[Decision]:
        return [d for d in self.decisions if d.attention == level]
