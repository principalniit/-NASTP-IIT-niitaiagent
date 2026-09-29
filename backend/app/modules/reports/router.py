import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ConflictError
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.organisations.dependencies import (
    ProjectAccess,
    ReportAccess,
    require_project,
    require_report,
)
from app.modules.organisations.permissions import Permission
from app.modules.reports import service
from app.modules.reports.models import PdfStatus, Report, ReportStatus
from app.modules.reports.schemas import ReportOut, ReportRequest

router = APIRouter(tags=["reports"])
Session = Annotated[AsyncSession, Depends(get_session)]
ReadReport = Annotated[ReportAccess, Depends(require_report(Permission.PROJECTS_READ))]


def _filename(report: Report, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", report.title).strip("-").lower()[:60] or "report"
    return f"{stem}-{report.created_at:%Y-%m-%d}.{extension}"


@router.post(
    "/projects/{project_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_report(
    body: ReportRequest,
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.REPORTS_GENERATE))],
) -> ReportOut:
    report = await service.request_report(session, access, body, get_request_meta(request))
    return ReportOut.model_validate(report)


@router.get("/projects/{project_id}/reports", response_model=Page[ReportOut])
async def list_reports(
    session: Session,
    paging: Annotated[PageParams, Depends(page_params)],
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))],
) -> Page[ReportOut]:
    items, total = await service.list_reports(session, access.project, paging)
    return Page(
        items=[ReportOut.model_validate(r) for r in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(access: ReadReport) -> ReportOut:
    return ReportOut.model_validate(access.report)


@router.get("/reports/{report_id}/html")
async def report_html(session: Session, access: ReadReport) -> Response:
    report = access.report
    html = await session.scalar(select(Report.html).where(Report.id == report.id))
    if report.status != ReportStatus.COMPLETED or not html:
        raise ConflictError("This report is not ready yet", code="not_ready")
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{_filename(report, "html")}"'},
    )


@router.get("/reports/{report_id}/pdf")
async def report_pdf(session: Session, access: ReadReport) -> Response:
    report = access.report
    pdf = await session.scalar(select(Report.pdf).where(Report.id == report.id))
    if report.pdf_status != PdfStatus.READY or not pdf:
        raise ConflictError(
            report.pdf_error or "The PDF for this report is not ready", code="pdf_not_ready"
        )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report, "pdf")}"'},
    )


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    request: Request,
    session: Session,
    access: Annotated[ReportAccess, Depends(require_report(Permission.REPORTS_GENERATE))],
) -> None:
    await service.delete_report(session, access, get_request_meta(request))
