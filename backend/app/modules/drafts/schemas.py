import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.drafts.models import ApprovalAction, DraftField, DraftSource, DraftStatus


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftCreate(_Strict):
    page_url: str = Field(
        min_length=1, max_length=2048, description="A URL or path on the project's website"
    )
    field: DraftField
    proposed_content: str = Field(min_length=1, max_length=20_000)
    reason: str = Field(min_length=5, max_length=2000)
    original_content: str | None = Field(default=None, max_length=20_000)
    issue_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class DraftEdit(_Strict):
    proposed_content: str = Field(min_length=1, max_length=20_000)
    reason: str = Field(min_length=5, max_length=2000)


class DraftDecision(_Strict):
    comment: str | None = Field(default=None, max_length=2000)
    source_reference: str | None = Field(default=None, max_length=2048)


class DraftRejection(_Strict):
    comment: str = Field(min_length=3, max_length=2000)


class DraftNote(_Strict):
    comment: str | None = Field(default=None, max_length=2000)


class DraftRollback(_Strict):
    comment: str = Field(min_length=3, max_length=2000)


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    page_url: str
    crawl_page_id: uuid.UUID | None
    field: DraftField
    original_content: str | None
    proposed_content: str
    reason: str
    evidence: dict[str, Any]
    source: DraftSource
    ai_analysis_id: uuid.UUID | None
    status: DraftStatus
    version: int
    protected: bool
    protected_reasons: list[str]
    created_by_id: uuid.UUID | None
    version_author_id: uuid.UUID | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    source_reference: str | None
    published_at: datetime | None
    rolled_back_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DraftVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    proposed_content: str
    reason: str
    source: DraftSource
    edited_by_id: uuid.UUID | None
    created_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    action: ApprovalAction
    from_status: str | None
    to_status: str
    actor_id: uuid.UUID | None
    comment: str | None
    source_reference: str | None
    created_at: datetime


class DraftDetail(DraftOut):
    versions: list[DraftVersionOut]
    trail: list[ApprovalOut]
    people: dict[str, str] = Field(default_factory=dict, description="user id to display name")
