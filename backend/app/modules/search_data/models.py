"""Search performance data imported from Google Search Console.

Rows are stored per integration (one Search Console property can cover several projects,
for example a domain property covers every subdomain) and matched to a project by the
page's host. Only what Google reported is stored; nothing is estimated.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPrimaryKey


class SyncStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SearchSync(UUIDPrimaryKey, Base):
    """One import of Search Console data, requested by a person or the daily schedule."""

    __tablename__ = "search_syncs"
    __table_args__ = (Index("ix_search_syncs_status_created", "status", "created_at"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SyncStatus] = mapped_column(
        Enum(
            SyncStatus,
            name="search_sync_status",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    page_day_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    query_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchPageDay(UUIDPrimaryKey, Base):
    """Clicks and impressions of one page on one day, as Search Console reported them."""

    __tablename__ = "search_page_days"
    __table_args__ = (
        Index("ix_search_page_days_scope", "organisation_id", "page_host", "day"),
        Index("ix_search_page_days_integration_day", "integration_id", "day"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    page: Mapped[str] = mapped_column(String(2048))
    page_host: Mapped[str] = mapped_column(String(253))
    clicks: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    # Google's average position for the page that day (1 is the top).
    position: Mapped[float] = mapped_column(Float)


class SearchPageQuery(UUIDPrimaryKey, Base):
    """Totals of one search query on one page over the latest sync's period."""

    __tablename__ = "search_page_queries"
    __table_args__ = (
        Index("ix_search_page_queries_scope", "organisation_id", "page_host"),
        Index("ix_search_page_queries_integration", "integration_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE")
    )
    sync_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_syncs.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[str] = mapped_column(String(2048))
    page_host: Mapped[str] = mapped_column(String(253))
    query: Mapped[str] = mapped_column(String(500))
    clicks: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    position: Mapped[float] = mapped_column(Float)
