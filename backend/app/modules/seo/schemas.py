import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.seo.models import ApprovalStatus, Category, ResolutionStatus, Severity


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    rule_id: str
    scope: str
    category: Category
    severity: Severity
    title: str
    description: str
    recommendation: str
    evidence: dict[str, Any]
    affected_url: str | None
    affected_urls: list[str]
    affected_page_count: int
    confidence: str
    effort: str
    priority_score: float
    priority_breakdown: list[dict[str, Any]]
    auto_fix_eligible: bool
    approval_status: ApprovalStatus
    resolution_status: ResolutionStatus
    first_detected_at: datetime
    last_detected_at: datetime
    first_crawl_id: uuid.UUID | None
    last_crawl_id: uuid.UUID | None
    resolved_at: datetime | None
    resolved_in_crawl_id: uuid.UUID | None
    recurrence_count: int
    triage_note: str | None


class IssueTriage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_status: Literal["open", "ignored"]
    note: str | None = Field(default=None, max_length=1000)


class IssueSummary(BaseModel):
    latest_crawl_id: uuid.UUID | None
    analysed_at: datetime | None
    open_total: int
    open_by_severity: dict[str, int]
    open_by_category: dict[str, int]
    ignored_total: int
    resolved_total: int
    new_in_latest: int
    resolved_in_latest: int


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crawl_job_id: uuid.UUID
    overall: float | None
    technical: float | None
    on_page: float | None
    content: float | None
    internal_linking: float | None
    structured_data: float | None
    pages_analysed: int
    breakdown: dict[str, Any]
    created_at: datetime


class ScorePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crawl_job_id: uuid.UUID
    created_at: datetime
    overall: float | None
    technical: float | None
    on_page: float | None
    content: float | None
    internal_linking: float | None
    structured_data: float | None


class SchemaFindingOut(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    page_url: str
    format: str
    schema_types: list[str]
    is_valid: bool
    errors: list[str]
    warnings: list[str]


class LinkRecommendationOut(BaseModel):
    id: uuid.UUID
    source_page_id: uuid.UUID
    source_url: str
    source_title: str | None
    target_page_id: uuid.UUID
    target_url: str
    target_title: str | None
    anchor_text: str
    reason: str
    snippet: str | None
    relevance: float


IssueSort = Literal["priority", "severity", "last_detected", "affected"]
