"""AI analyses (every request to the model, with the evidence it was given) and the
recommendations derived from them."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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

from app.core.database import Base, UUIDPrimaryKey


class AIKind(enum.StrEnum):
    MANAGEMENT_SUMMARY = "management_summary"
    ISSUE_EXPLANATION = "issue_explanation"
    PAGE_PLAN = "page_plan"
    METADATA_DRAFT = "metadata_draft"
    CONTENT_OUTLINE = "content_outline"
    QUESTION = "question"


class AIStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationStatus(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class AIAnalysis(UUIDPrimaryKey, Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("ix_ai_analyses_status_created", "status", "created_at"),
        Index("ix_ai_analyses_project_kind_created", "project_id", "kind", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    kind: Mapped[AIKind] = mapped_column(_enum(AIKind, "ai_kind"))
    status: Mapped[AIStatus] = mapped_column(_enum(AIStatus, "ai_status"))
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    # The exact evidence given to the model, kept so every output can be audited.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    grounding: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # Model time and token counts as reported by the provider (AIUsage); None before
    # the model was called.
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SeoRecommendation(UUIDPrimaryKey, Base):
    """A grounded, AI-worded recommendation linked to issues. Never applied automatically."""

    __tablename__ = "seo_recommendations"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    ai_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_analyses.id", ondelete="CASCADE"), index=True
    )
    issue_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    page_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    steps: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[RecommendationStatus] = mapped_column(
        _enum(RecommendationStatus, "recommendation_status"),
        default=RecommendationStatus.OPEN,
        server_default=RecommendationStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackRating(enum.StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class FeedbackReason(enum.StrEnum):
    WRONG = "wrong"
    OFF_TOPIC = "off_topic"
    VAGUE = "vague"
    MISSED_DATA = "missed_data"
    OTHER = "other"


class AIFeedback(UUIDPrimaryKey, Base):
    """One person's verdict on one AI result. Not-helpful results become test cases."""

    __tablename__ = "ai_feedback"
    __table_args__ = (UniqueConstraint("ai_analysis_id", "user_id"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    ai_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_analyses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rating: Mapped[FeedbackRating] = mapped_column(_enum(FeedbackRating, "feedback_rating"))
    reason: Mapped[FeedbackReason | None] = mapped_column(_enum(FeedbackReason, "feedback_reason"))
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
