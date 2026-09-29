"""Report requests, listing and generation. Generation runs in the worker."""

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.core.errors import AppError, ConflictError, RateLimitedError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.organisations.dependencies import ProjectAccess, ReportAccess
from app.modules.organisations.models import Organisation
from app.modules.plans.service import enforce
from app.modules.projects.models import Project
from app.modules.reports import builder, render
from app.modules.reports.models import PdfStatus, Report, ReportStatus
from app.modules.reports.pdf import PdfUnavailableError, render_pdf
from app.modules.reports.schemas import ReportRequest
from app.modules.seo.service import latest_analysed_crawl

logger = logging.getLogger(__name__)
MAX_ACTIVE_PER_ORG = 3


async def request_report(
    session: AsyncSession, access: ProjectAccess, body: ReportRequest, meta: RequestMeta
) -> Report:
    project = access.project
    crawl = await latest_analysed_crawl(session, project.id, project.organisation_id)
    if crawl is None:
        raise ConflictError(
            "Crawl and analyse this project before generating a report", code="not_analysed"
        )
    active = (
        await session.scalar(
            select(func.count()).where(
                Report.organisation_id == project.organisation_id,
                Report.status.in_([ReportStatus.QUEUED, ReportStatus.RUNNING]),
            )
        )
        or 0
    )
    await enforce(session, project.organisation_id, "reports_per_month")
    if active >= MAX_ACTIVE_PER_ORG:
        raise RateLimitedError("Several reports are already being generated. Try again shortly.")
    report = Report(
        organisation_id=project.organisation_id,
        project_id=project.id,
        crawl_job_id=crawl.id,
        title=body.title or f"SEO health report: {project.name}",
        status=ReportStatus.QUEUED,
        include_ai=body.include_ai,
        requested_by_id=access.user.id,
    )
    session.add(report)
    await session.flush()
    audit.record(
        session,
        action="report.requested",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="report",
        target_id=report.id,
        details={"include_ai": body.include_ai, "crawl_job_id": str(crawl.id)},
    )
    await session.commit()
    await session.refresh(report)
    return report


async def list_reports(
    session: AsyncSession, project: Project, params: PageParams
) -> tuple[list[Report], int]:
    query = select(Report).where(
        Report.project_id == project.id, Report.organisation_id == project.organisation_id
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(Report.created_at.desc()).offset(params.offset).limit(params.page_size)
    )
    return list(rows), total


async def delete_report(session: AsyncSession, access: ReportAccess, meta: RequestMeta) -> None:
    report = access.report
    if report.status in (ReportStatus.QUEUED, ReportStatus.RUNNING):
        raise ConflictError("A report cannot be deleted while it is being generated")
    audit.record(
        session,
        action="report.deleted",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=report.organisation_id,
        target_type="report",
        target_id=report.id,
        details={"title": report.title},
    )
    await session.delete(report)
    await session.commit()


async def run_report(
    report_id: uuid.UUID, *, factory: async_sessionmaker[AsyncSession] | None = None
) -> ReportStatus:
    factory = factory or get_session_factory()
    async with factory() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise LookupError(f"Report {report_id} not found")
        started = time.monotonic()
        report.started_at = report.started_at or datetime.now(UTC)
        try:
            data = render.finalise(await builder.build(session, report))
        except AppError as exc:
            report.status, report.error = ReportStatus.FAILED, exc.message
            report.pdf_status = PdfStatus.FAILED
            report.finished_at = datetime.now(UTC)
            await session.commit()
            return report.status
        org = await session.get(Organisation, report.organisation_id)
        logo = await render.fetch_logo(org.logo_url if org else None)
        data["branding"]["logo_embedded"] = logo is not None
        html = render.render_html(data, logo)
        report.data, report.html = data, html
        try:
            report.pdf = await render_pdf(
                html,
                data["branding"].get("footer_text")
                or data["branding"].get("display_name")
                or data["meta"]["organisation"],
            )
            report.pdf_status, report.pdf_error = PdfStatus.READY, None
        except PdfUnavailableError as exc:
            report.pdf_status, report.pdf_error = PdfStatus.UNAVAILABLE, str(exc)
        except Exception:
            logger.exception("PDF rendering failed", extra={"report_id": str(report.id)})
            report.pdf_status = PdfStatus.FAILED
            report.pdf_error = "The PDF could not be produced. The HTML report is available."
        report.status = ReportStatus.COMPLETED
        report.finished_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "Report generated",
            extra={
                "report_id": str(report.id),
                "pdf_status": report.pdf_status.value,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return report.status
