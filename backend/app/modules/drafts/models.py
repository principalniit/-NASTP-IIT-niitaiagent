"""Content drafts, their version history and the approval trail.

The platform never changes a website. "Published" records that a person applied an
approved draft outside the platform; "rolled back" records that they reverted it.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, Timestamps, UUIDPrimaryKey


class DraftField(enum.StrEnum):
    TITLE = "title"
    META_DESCRIPTION = "meta_description"
    H1 = "h1"
    CONTENT_OUTLINE = "content_outline"
    CONTENT_SECTION = "content_section"


class DraftStatus(enum.StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"


class DraftSource(enum.StrEnum):
    AI = "ai"
    HUMAN = "human"


class ApprovalAction(enum.StrEnum):
    CREATED = "created"
    EDITED = "edited"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    REOPENED = "reopened"
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class ContentDraft(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "content_drafts"
    __table_args__ = (Index("ix_content_drafts_project_status", "project_id", "status"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    page_url: Mapped[str] = mapped_column(String(2048))
    crawl_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="SET NULL")
    )
    field: Mapped[DraftField] = mapped_column(_enum(DraftField, "draft_field"))
    # The content as crawled, preserved for comparison and rollback.
    original_content: Mapped[str | None] = mapped_column(Text)
    proposed_content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    source: Mapped[DraftSource] = mapped_column(_enum(DraftSource, "draft_source"))
    ai_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_analyses.id", ondelete="SET NULL")
    )
    status: Mapped[DraftStatus] = mapped_column(_enum(DraftStatus, "draft_status"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Touches official facts (fees, dates, eligibility, figures): approval needs a source.
    protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    protected_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Author of the current version; this person may not approve it.
    version_author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_reference: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentDraftVersion(UUIDPrimaryKey, Base):
    __tablename__ = "content_draft_versions"
    __table_args__ = (UniqueConstraint("draft_id", "version"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_drafts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    proposed_content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[DraftSource] = mapped_column(_enum(DraftSource, "draft_version_source"))
    edited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(UUIDPrimaryKey, Base):
    """Append-only trail of every status change and edit of a draft."""

    __tablename__ = "approvals"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_drafts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[ApprovalAction] = mapped_column(_enum(ApprovalAction, "approval_action"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
