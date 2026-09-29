import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlPage, CrawlStatus
from app.modules.organisations.dependencies import CrawlAccess, IssueAccess
from app.modules.seo.models import (
    Category,
    InternalLinkRecommendation,
    ResolutionStatus,
    SchemaFinding,
    SeoIssue,
    SeoScore,
    Severity,
)
from app.modules.seo.schemas import (
    IssueSort,
    IssueSummary,
    IssueTriage,
    LinkRecommendationOut,
    SchemaFindingOut,
)

SEVERITY_ORDER = case(
    {s.value: i for i, s in enumerate(Severity)}, value=SeoIssue.severity, else_=99
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_issues(
    session: AsyncSession,
    project_id: uuid.UUID,
    organisation_id: uuid.UUID,
    params: PageParams,
    *,
    status: ResolutionStatus | None,
    severity: Severity | None,
    category: Category | None,
    rule_id: str | None,
    q: str | None,
    sort: IssueSort,
    order: str,
) -> tuple[list[SeoIssue], int]:
    query = select(SeoIssue).where(
        SeoIssue.project_id == project_id, SeoIssue.organisation_id == organisation_id
    )
    if status:
        query = query.where(SeoIssue.resolution_status == status)
    if severity:
        query = query.where(SeoIssue.severity == severity)
    if category:
        query = query.where(SeoIssue.category == category)
    if rule_id:
        query = query.where(SeoIssue.rule_id == rule_id)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        query = query.where(
            or_(
                SeoIssue.title.ilike(pattern, escape="\\"),
                SeoIssue.affected_url.ilike(pattern, escape="\\"),
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    columns = {
        "priority": SeoIssue.priority_score,
        "severity": SEVERITY_ORDER,
        "last_detected": SeoIssue.last_detected_at,
        "affected": SeoIssue.affected_page_count,
    }
    column = columns[sort]
    # "desc" means most important first for every sort; severity order is inverted.
    descending = order == "desc"
    if sort == "severity":
        descending = not descending
    ordered = column.desc() if descending else column.asc()
    rows = await session.scalars(
        query.order_by(ordered, SeoIssue.priority_score.desc(), SeoIssue.id)
        .offset(params.offset)
        .limit(params.page_size)
    )
    return list(rows), total


async def latest_analysed_crawl(
    session: AsyncSession, project_id: uuid.UUID, organisation_id: uuid.UUID
) -> CrawlJob | None:
    job: CrawlJob | None = await session.scalar(
        select(CrawlJob)
        .where(
            CrawlJob.project_id == project_id,
            CrawlJob.organisation_id == organisation_id,
            CrawlJob.analysis_status == AnalysisStatus.COMPLETED,
        )
        .order_by(CrawlJob.created_at.desc())
        .limit(1)
    )
    return job


async def summary(
    session: AsyncSession, project_id: uuid.UUID, organisation_id: uuid.UUID
) -> IssueSummary:
    base = (
        select(SeoIssue)
        .where(SeoIssue.project_id == project_id, SeoIssue.organisation_id == organisation_id)
        .subquery()
    )
    by_status: dict[object, int] = dict(
        (
            await session.execute(
                select(base.c.resolution_status, func.count()).group_by(base.c.resolution_status)
            )
        ).all()
    )
    open_rows = select(base).where(base.c.resolution_status == ResolutionStatus.OPEN).subquery()
    by_severity: dict[object, int] = dict(
        (
            await session.execute(
                select(open_rows.c.severity, func.count()).group_by(open_rows.c.severity)
            )
        ).all()
    )
    by_category: dict[object, int] = dict(
        (
            await session.execute(
                select(open_rows.c.category, func.count()).group_by(open_rows.c.category)
            )
        ).all()
    )
    latest = await latest_analysed_crawl(session, project_id, organisation_id)
    new = resolved_latest = 0
    if latest is not None:
        new = (
            await session.scalar(
                select(func.count()).where(
                    base.c.first_crawl_id == latest.id,
                    base.c.resolution_status != ResolutionStatus.RESOLVED,
                )
            )
            or 0
        )
        resolved_latest = (
            await session.scalar(
                select(func.count()).where(base.c.resolved_in_crawl_id == latest.id)
            )
            or 0
        )

    def names(counts: dict[object, int]) -> dict[str, int]:
        return {str(getattr(k, "value", k)): v for k, v in counts.items()}

    statuses = names(by_status)
    return IssueSummary(
        latest_crawl_id=latest.id if latest else None,
        analysed_at=latest.analysed_at if latest else None,
        open_total=statuses.get("open", 0),
        open_by_severity={s.value: names(by_severity).get(s.value, 0) for s in Severity},
        open_by_category={c.value: names(by_category).get(c.value, 0) for c in Category},
        ignored_total=statuses.get("ignored", 0),
        resolved_total=statuses.get("resolved", 0),
        new_in_latest=new,
        resolved_in_latest=resolved_latest,
    )


async def triage(
    session: AsyncSession, access: IssueAccess, body: IssueTriage, meta: RequestMeta
) -> SeoIssue:
    issue = access.issue
    if issue.resolution_status == ResolutionStatus.RESOLVED:
        raise ConflictError("Resolved issues change only when a new crawl detects them again")
    previous = issue.resolution_status
    issue.resolution_status = ResolutionStatus(body.resolution_status)
    issue.triage_note = body.note
    issue.triaged_by_id = access.user.id
    audit.record(
        session,
        action="issue.triaged",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=issue.organisation_id,
        target_type="seo_issue",
        target_id=issue.id,
        details={"from": previous.value, "to": body.resolution_status, "rule_id": issue.rule_id},
    )
    await session.commit()
    await session.refresh(issue)
    return issue


async def get_score(session: AsyncSession, crawl: CrawlJob) -> SeoScore:
    score: SeoScore | None = await session.scalar(
        select(SeoScore).where(
            SeoScore.crawl_job_id == crawl.id, SeoScore.organisation_id == crawl.organisation_id
        )
    )
    if score is None:
        raise NotFoundError("This crawl has not been analysed yet")
    return score


async def score_history(
    session: AsyncSession, project_id: uuid.UUID, organisation_id: uuid.UUID
) -> list[SeoScore]:
    rows = await session.scalars(
        select(SeoScore)
        .where(SeoScore.project_id == project_id, SeoScore.organisation_id == organisation_id)
        .order_by(SeoScore.created_at.desc())
        .limit(50)
    )
    return list(reversed(list(rows)))


async def schema_findings(
    session: AsyncSession, crawl: CrawlJob, params: PageParams, invalid_only: bool
) -> tuple[list[SchemaFindingOut], int]:
    query = (
        select(SchemaFinding, CrawlPage.url)
        .join(CrawlPage, CrawlPage.id == SchemaFinding.page_id)
        .where(
            SchemaFinding.crawl_job_id == crawl.id,
            SchemaFinding.organisation_id == crawl.organisation_id,
        )
    )
    if invalid_only:
        query = query.where(SchemaFinding.is_valid.is_(False))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(
        query.order_by(SchemaFinding.is_valid, CrawlPage.url)
        .offset(params.offset)
        .limit(params.page_size)
    )
    return [
        SchemaFindingOut(
            id=f.id,
            page_id=f.page_id,
            page_url=url,
            format=f.format,
            schema_types=f.schema_types,
            is_valid=f.is_valid,
            errors=f.errors,
            warnings=f.warnings,
        )
        for f, url in rows.all()
    ], total


async def link_recommendations(
    session: AsyncSession, crawl: CrawlJob, params: PageParams
) -> tuple[list[LinkRecommendationOut], int]:
    source = aliased(CrawlPage)
    target = aliased(CrawlPage)
    query = (
        select(InternalLinkRecommendation, source.url, source.title, target.url, target.title)
        .join(source, source.id == InternalLinkRecommendation.source_page_id)
        .join(target, target.id == InternalLinkRecommendation.target_page_id)
        .where(
            InternalLinkRecommendation.crawl_job_id == crawl.id,
            InternalLinkRecommendation.organisation_id == crawl.organisation_id,
        )
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(
        query.order_by(InternalLinkRecommendation.relevance.desc(), target.url)
        .offset(params.offset)
        .limit(params.page_size)
    )
    return [
        LinkRecommendationOut(
            id=r.id,
            source_page_id=r.source_page_id,
            source_url=s_url,
            source_title=s_title,
            target_page_id=r.target_page_id,
            target_url=t_url,
            target_title=t_title,
            anchor_text=r.anchor_text,
            reason=r.reason,
            snippet=r.evidence.get("snippet"),
            relevance=r.relevance,
        )
        for r, s_url, s_title, t_url, t_title in rows.all()
    ], total


async def request_analysis(
    session: AsyncSession, access: CrawlAccess, meta: RequestMeta
) -> CrawlJob:
    job = await session.get(CrawlJob, access.crawl.id, with_for_update=True)
    if job is None or job.status != CrawlStatus.COMPLETED:
        raise ConflictError("Only completed crawls can be analysed")
    if job.pages_pruned_at is not None:
        raise ConflictError(
            "This crawl's page data was removed under the data retention policy. Start a new crawl."
        )
    if job.analysis_status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING):
        raise ConflictError("An analysis of this crawl is already queued or running")
    newer = await session.scalar(
        select(CrawlJob.id).where(
            CrawlJob.project_id == job.project_id,
            CrawlJob.created_at > job.created_at,
            CrawlJob.status == CrawlStatus.COMPLETED,
        )
    )
    if newer is not None:
        raise ConflictError("Only the most recent completed crawl can be analysed")
    job.analysis_status = AnalysisStatus.QUEUED
    job.analysis_error = None
    job.updated_at = datetime.now(UTC)
    audit.record(
        session,
        action="crawl.analysis_requested",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=job.organisation_id,
        target_type="crawl",
        target_id=job.id,
    )
    await session.commit()
    await session.refresh(job)
    return job
