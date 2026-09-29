"""Management reports. Each report is a stored snapshot: the data, the rendered HTML and,
when a renderer is available, a PDF. Regenerating creates a new report."""

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
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPrimaryKey


class ReportStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PdfStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"  # no PDF renderer installed; the HTML report still works
    FAILED = "failed"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class Report(UUIDPrimaryKey, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_project_created", "project_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReportStatus] = mapped_column(_enum(ReportStatus, "report_status"))
    include_ai: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # The facts the report was rendered from, kept so the report can be explained later.
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    html: Mapped[str | None] = mapped_column(Text, deferred=True)
    pdf: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    pdf_status: Mapped[PdfStatus] = mapped_column(
        _enum(PdfStatus, "pdf_status"),
        default=PdfStatus.PENDING,
        server_default=PdfStatus.PENDING.value,
    )
    pdf_error: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
