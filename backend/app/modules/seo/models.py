"""SEO engine results: issues (tracked across crawls), scores, structured-data findings
and internal-link recommendations."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, Timestamps, UUIDPrimaryKey


class Severity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class Category(enum.StrEnum):
    TECHNICAL = "technical"
    ON_PAGE = "on_page"
    CONTENT = "content"
    INTERNAL_LINKING = "internal_linking"
    STRUCTURED_DATA = "structured_data"


class ResolutionStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ApprovalStatus(enum.StrEnum):
    # No change has been proposed yet. Drafts and approvals arrive in Phase 4.
    NONE = "none"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class SeoIssue(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "seo_issues"
    __table_args__ = (
        UniqueConstraint("project_id", "issue_key"),
        Index(
            "ix_seo_issues_project_status_priority",
            "project_id",
            "resolution_status",
            "priority_score",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # Stable identity across crawls: rule plus the URL, group or site it concerns.
    issue_key: Mapped[str] = mapped_column(String(200))
    rule_id: Mapped[str] = mapped_column(String(80), index=True)
    # page, group or site: decides what a later crawl must re-examine before resolving.
    scope: Mapped[str] = mapped_column(String(8))
    category: Mapped[Category] = mapped_column(_enum(Category, "seo_category"))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "seo_severity"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    affected_url: Mapped[str | None] = mapped_column(String(2048))
    affected_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    affected_page_count: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(16))
    effort: Mapped[str] = mapped_column(String(16))
    priority_score: Mapped[float] = mapped_column(Float)
    priority_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    auto_fix_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        _enum(ApprovalStatus, "seo_approval_status"),
        default=ApprovalStatus.NONE,
        server_default=ApprovalStatus.NONE.value,
    )
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        _enum(ResolutionStatus, "seo_resolution_status"),
        default=ResolutionStatus.OPEN,
        server_default=ResolutionStatus.OPEN.value,
    )
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_crawl_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    last_crawl_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL"), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_in_crawl_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    triage_note: Mapped[str | None] = mapped_column(String(1000))
    triaged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class SeoScore(UUIDPrimaryKey, Base):
    __tablename__ = "seo_scores"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), unique=True
    )
    overall: Mapped[float | None] = mapped_column(Float)
    technical: Mapped[float | None] = mapped_column(Float)
    on_page: Mapped[float | None] = mapped_column(Float)
    content: Mapped[float | None] = mapped_column(Float)
    internal_linking: Mapped[float | None] = mapped_column(Float)
    structured_data: Mapped[float | None] = mapped_column(Float)
    pages_analysed: Mapped[int] = mapped_column(Integer)
    # Per category: weight, penalty and each rule's contribution, for transparency.
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SchemaFinding(UUIDPrimaryKey, Base):
    __tablename__ = "schema_findings"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(16))  # json_ld | microdata
    schema_types: Mapped[list[str]] = mapped_column(JSONB)
    is_valid: Mapped[bool] = mapped_column(Boolean)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class InternalLinkRecommendation(UUIDPrimaryKey, Base):
    __tablename__ = "internal_link_recommendations"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True
    )
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE")
    )
    target_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE")
    )
    anchor_text: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    relevance: Mapped[float] = mapped_column(Float)
