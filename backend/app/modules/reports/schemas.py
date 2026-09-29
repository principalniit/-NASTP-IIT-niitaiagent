import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reports.models import PdfStatus, ReportStatus


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200)
    include_ai: bool = True


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    crawl_job_id: uuid.UUID | None
    title: str
    status: ReportStatus
    include_ai: bool
    pdf_status: PdfStatus
    pdf_error: str | None
    error: str | None
    requested_by_id: uuid.UUID | None
    created_at: datetime
    finished_at: datetime | None
