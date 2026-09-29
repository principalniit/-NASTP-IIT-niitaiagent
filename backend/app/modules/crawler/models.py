"""Crawl jobs (also the work queue), crawled pages and discovered links."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, Timestamps, UUIDPrimaryKey


class CrawlStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = (CrawlStatus.QUEUED, CrawlStatus.RUNNING, CrawlStatus.CANCELLING)


class FetchStatus(enum.StrEnum):
    FETCHED = "fetched"
    NOT_MODIFIED = "not_modified"
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    BLOCKED_DESTINATION = "blocked_destination"
    REDIRECT_OUT_OF_SCOPE = "redirect_out_of_scope"
    SKIPPED_CONTENT_TYPE = "skipped_content_type"
    TOO_LARGE = "too_large"
    ERROR = "error"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class CrawlJob(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        # At most one queued or running crawl per project.
        Index(
            "uq_crawl_jobs_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'cancelling')"),
        ),
        Index("ix_crawl_jobs_status_created", "status", "created_at"),
        Index("ix_crawl_jobs_project_created", "project_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[CrawlStatus] = mapped_column(_enum(CrawlStatus, "crawl_status"))
    incremental: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    previous_crawl_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    # Snapshot of the settings the crawl ran with, so later setting changes do not
    # rewrite history.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)

    pages_discovered: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    robots_status: Mapped[str | None] = mapped_column(String(32))
    sitemaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    sitemap_url_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    error_message: Mapped[str | None] = mapped_column(Text)

    worker_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlPage(UUIDPrimaryKey, Base):
    __tablename__ = "crawl_pages"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "url"),
        Index("ix_crawl_pages_job_status", "crawl_job_id", "status_code"),
        Index("ix_crawl_pages_job_hash", "crawl_job_id", "content_hash"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str | None] = mapped_column(String(2048))
    depth: Mapped[int | None] = mapped_column(Integer)
    discovered_via: Mapped[str] = mapped_column(String(16))
    fetch_status: Mapped[FetchStatus] = mapped_column(_enum(FetchStatus, "fetch_status"))
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(200))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    content_length: Mapped[int | None] = mapped_column(Integer)
    redirect_chain: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(100))

    title: Mapped[str | None] = mapped_column(Text)
    title_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    meta_description: Mapped[str | None] = mapped_column(Text)
    meta_description_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    meta_robots: Mapped[str | None] = mapped_column(String(300))
    x_robots_tag: Mapped[str | None] = mapped_column(String(300))
    is_noindex: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_nofollow: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    canonical_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lang: Mapped[str | None] = mapped_column(String(35))
    headings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    h1_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    word_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    images: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    image_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    images_missing_alt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    structured_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    hreflang: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    internal_links_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    external_links_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inlinks_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    in_sitemap: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_orphan: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlLink(UUIDPrimaryKey, Base):
    __tablename__ = "crawl_links"
    __table_args__ = (Index("ix_crawl_links_job_target", "crawl_job_id", "target_url"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True
    )
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE"), index=True
    )
    target_url: Mapped[str] = mapped_column(String(2048))
    target_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="SET NULL"), index=True
    )
    is_internal: Mapped[bool] = mapped_column(Boolean)
    nofollow: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    anchor_text: Mapped[str | None] = mapped_column(String(300))
