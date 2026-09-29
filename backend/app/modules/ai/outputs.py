"""JSON shapes the model must return. Lengths are capped so output stays reviewable."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = str


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KeyFinding(_Out):
    statement: str = Field(min_length=3, max_length=400)
    issue_ids: list[str] = Field(default_factory=list, max_length=10)


class PriorityAction(_Out):
    action: str = Field(min_length=3, max_length=300)
    reason: str = Field(min_length=3, max_length=400)
    issue_ids: list[str] = Field(default_factory=list, max_length=10)


class ManagementSummaryOutput(_Out):
    headline: str = Field(min_length=3, max_length=200)
    overview: str = Field(min_length=10, max_length=1500)
    key_findings: list[KeyFinding] = Field(min_length=1, max_length=8)
    priorities: list[PriorityAction] = Field(min_length=1, max_length=6)
    changes_since_previous: str | None = Field(default=None, max_length=800)
    data_limitations: list[str] = Field(default_factory=list, max_length=6)


class IssueExplanationOutput(_Out):
    explanation: str = Field(min_length=10, max_length=1500)
    why_it_matters: str = Field(min_length=10, max_length=800)
    steps: list[str] = Field(min_length=1, max_length=8)
    how_to_verify: str = Field(min_length=5, max_length=400)
    caveats: list[str] = Field(default_factory=list, max_length=5)
    issue_ids: list[str] = Field(default_factory=list, max_length=5)


class PageImprovement(_Out):
    area: Literal[
        "title", "meta_description", "headings", "content", "links", "images",
        "structured_data", "technical",
    ]  # fmt: skip
    suggestion: str = Field(min_length=5, max_length=400)
    issue_ids: list[str] = Field(default_factory=list, max_length=10)


class PagePlanOutput(_Out):
    summary: str = Field(min_length=5, max_length=600)
    improvements: list[PageImprovement] = Field(default_factory=list, max_length=10)


class MetadataDraftOutput(_Out):
    title: str = Field(min_length=3, max_length=120)
    meta_description: str = Field(min_length=10, max_length=320)
    rationale: str = Field(min_length=5, max_length=600)
    facts_used: list[str] = Field(default_factory=list, max_length=10)


class OutlineSection(_Out):
    heading: str = Field(min_length=2, max_length=120)
    points: list[str] = Field(default_factory=list, max_length=6)
    facts_needed: list[str] = Field(default_factory=list, max_length=5)


class ContentOutlineOutput(_Out):
    purpose: str = Field(min_length=5, max_length=300)
    sections: list[OutlineSection] = Field(min_length=1, max_length=8)
    questions_for_editor: list[str] = Field(default_factory=list, max_length=6)


class AgentStep(_Out):
    action: Literal["call_tool", "answer"]
    tool: str | None = Field(default=None, max_length=50)
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = Field(default=None, max_length=2000)
    issue_ids: list[str] = Field(default_factory=list, max_length=10)


class AgentAnswer(_Out):
    answer: str = Field(min_length=1, max_length=2000)
    issue_ids: list[str] = Field(default_factory=list, max_length=10)
    tools_used: list[str] = Field(default_factory=list)
