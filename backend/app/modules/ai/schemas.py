import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ai.models import (
    AIKind,
    AIStatus,
    FeedbackRating,
    FeedbackReason,
    RecommendationStatus,
)
from app.providers.interfaces import AIUsage


class AIStatusOut(BaseModel):
    enabled: bool
    provider: str
    model: str | None
    status: Literal["disabled", "available", "unavailable"]
    detail: str | None


class AIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AIKind
    issue_id: uuid.UUID | None = None
    page_url: str | None = Field(default=None, max_length=2048)
    question: str | None = Field(default=None, min_length=3, max_length=500)
    goal: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _subject(self) -> "AIRequest":
        needs = {
            AIKind.ISSUE_EXPLANATION: ("issue_id", self.issue_id),
            AIKind.PAGE_PLAN: ("page_url", self.page_url),
            AIKind.METADATA_DRAFT: ("page_url", self.page_url),
            AIKind.CONTENT_OUTLINE: ("page_url", self.page_url),
            AIKind.QUESTION: ("question", self.question),
        }
        if self.kind in needs and not needs[self.kind][1]:
            raise ValueError(f"{needs[self.kind][0]} is required for {self.kind.value}")
        return self


class AIAnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    crawl_job_id: uuid.UUID | None
    kind: AIKind
    status: AIStatus
    subject_type: str
    subject_id: str | None
    params: dict[str, Any]
    provider: str | None
    model: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    requested_by_id: uuid.UUID | None


class AIAnalysisOut(AIAnalysisSummary):
    prompt_version: str | None
    evidence: dict[str, Any]
    output: dict[str, Any] | None
    grounding: dict[str, Any]
    attempts: int
    duration_ms: int | None
    metrics: AIUsage | None = None
    # The signed-in person's own feedback on this result, if any.
    my_feedback: "FeedbackOut | None" = None
    draft_ids: list[uuid.UUID] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    ai_analysis_id: uuid.UUID
    issue_ids: list[str]
    page_url: str | None
    title: str
    body: str
    steps: list[str]
    status: RecommendationStatus
    created_at: datetime


class RecommendationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: RecommendationStatus


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: FeedbackRating
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_only_when_not_helpful(self) -> "FeedbackIn":
        if self.rating == FeedbackRating.HELPFUL:
            self.reason = None
        if self.comment is not None:
            self.comment = self.comment.strip() or None
        return self


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: FeedbackRating
    reason: FeedbackReason | None
    comment: str | None
    updated_at: datetime


AIAnalysisOut.model_rebuild()
