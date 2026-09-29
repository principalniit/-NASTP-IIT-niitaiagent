"""Data retention. Off unless an organisation owner sets it in organisation settings.

- Page-level crawl data (pages, links, structured-data results, link suggestions) is
  deleted for crawls older than the newest `keep_crawls` per project. The crawl record,
  its score and the issue history stay, so trends and reports remain meaningful. The
  latest analysed crawl is never pruned.
- Reports older than `delete_reports_after_days` are deleted.
Every run that deletes anything is audit-logged per organisation.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.modules.audit_logs import service as audit
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlPage, CrawlStatus
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.projects.models import Project
from app.modules.reports.models import Report, ReportStatus

logger = logging.getLogger(__name__)
FINISHED = (CrawlStatus.COMPLETED, CrawlStatus.FAILED, CrawlStatus.CANCELLED)


async def _prune_project(session: AsyncSession, project: Project, keep: int, now: datetime) -> int:
    crawls = list(
        await session.scalars(
            select(CrawlJob)
            .where(
                CrawlJob.project_id == project.id,
                CrawlJob.organisation_id == project.organisation_id,
                CrawlJob.status.in_(FINISHED),
            )
            .order_by(CrawlJob.created_at.desc())
        )
    )
    latest_analysed = next(
        (c.id for c in crawls if c.analysis_status == AnalysisStatus.COMPLETED), None
    )
    pruned = 0
    for crawl in crawls[keep:]:
        if crawl.pages_pruned_at is not None or crawl.id == latest_analysed:
            continue
        await session.execute(delete(CrawlPage).where(CrawlPage.crawl_job_id == crawl.id))
        crawl.pages_pruned_at = now
        pruned += 1
    return pruned


async def apply_retention(
    factory: async_sessionmaker[AsyncSession] | None = None, now: datetime | None = None
) -> dict[str, int]:
    factory = factory or get_session_factory()
    now = now or datetime.now(UTC)
    totals = {"crawls_pruned": 0, "reports_deleted": 0}
    async with factory() as session:
        for org in await session.scalars(select(Organisation)):
            policy = OrganisationSettings.model_validate(org.settings).data_retention
            if policy.keep_crawls is None and policy.delete_reports_after_days is None:
                continue
            pruned = deleted = 0
            if policy.keep_crawls is not None:
                projects = await session.scalars(
                    select(Project).where(Project.organisation_id == org.id)
                )
                for project in projects:
                    pruned += await _prune_project(session, project, policy.keep_crawls, now)
            if policy.delete_reports_after_days is not None:
                cutoff = now - timedelta(days=policy.delete_reports_after_days)
                result = await session.execute(
                    delete(Report).where(
                        Report.organisation_id == org.id,
                        Report.created_at < cutoff,
                        Report.status.in_([ReportStatus.COMPLETED, ReportStatus.FAILED]),
                    )
                )
                deleted = int(getattr(result, "rowcount", 0) or 0)
            if pruned or deleted:
                audit.record(
                    session,
                    action="retention.applied",
                    actor_id=None,
                    organisation_id=org.id,
                    details={"crawls_pruned": pruned, "reports_deleted": deleted},
                )
                logger.info(
                    "Retention applied",
                    extra={
                        "organisation_id": str(org.id),
                        "crawls_pruned": pruned,
                        "reports_deleted": deleted,
                    },
                )
            totals["crawls_pruned"] += pruned
            totals["reports_deleted"] += deleted
        await session.commit()
    return totals
