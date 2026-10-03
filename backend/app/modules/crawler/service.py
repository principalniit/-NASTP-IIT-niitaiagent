import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import ConflictError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.models import (
    ACTIVE_STATUSES,
    AnalysisStatus,
    CrawlJob,
    CrawlLink,
    CrawlPage,
    CrawlStatus,
    FetchStatus,
)
from app.modules.crawler.schemas import (
    BrokenLinkOut,
    CrawlJobOut,
    CrawlPageDetail,
    CrawlSummary,
    DuplicateGroup,
    LinkOut,
    PageSort,
    StatusClass,
)
from app.modules.crawler.urls import host_of, port_of, www_twin
from app.modules.organisations.dependencies import CrawlAccess, ProjectAccess
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.plans.service import enforce, pages_cap
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.projects.service import get_settings_row

FAILED_FETCHES = (FetchStatus.ERROR, FetchStatus.TOO_LARGE, FetchStatus.BLOCKED_DESTINATION)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def to_out(job: CrawlJob, project_name: str | None = None) -> CrawlJobOut:
    out = CrawlJobOut.model_validate(job)
    out.project_name = project_name
    return out


async def build_config(session: AsyncSession, project: Project) -> CrawlConfig:
    org = await session.get(Organisation, project.organisation_id)
    caps = OrganisationSettings.model_validate(org.settings if org else {}).crawl_limits
    settings = ProjectSettingsData.model_validate(
        (await get_settings_row(session, project)).settings
    )
    crawl = settings.crawl
    plan_pages = await pages_cap(session, org) if org else None
    root_host = host_of(project.root_url)
    port = port_of(project.root_url)
    # The site's www and bare names are one site: either may redirect to the other.
    twin = www_twin(root_host)
    hosts = {root_host, *settings.allowed_extra_hosts, *([twin] if twin else [])}
    return CrawlConfig(
        root_url=project.root_url,
        allowed_hosts=sorted(hosts),
        excluded_paths=settings.excluded_paths,
        max_pages=min(crawl.max_pages, caps.max_pages, plan_pages or caps.max_pages),
        max_depth=min(crawl.max_depth, caps.max_depth),
        concurrency=min(crawl.concurrency, caps.max_concurrency),
        timeout_seconds=crawl.timeout_seconds,
        delay_ms=crawl.delay_ms,
        user_agent=crawl.user_agent,
        render_javascript=crawl.render_javascript,
        extra_ports=[] if port in (80, 443) else [port],
    )


async def start(
    session: AsyncSession, access: ProjectAccess, incremental: bool, meta: RequestMeta
) -> CrawlJob:
    project = access.project
    await enforce(session, project.organisation_id, "crawls_per_month")
    previous_id = None
    if incremental:
        previous_id = await session.scalar(
            select(CrawlJob.id)
            .where(
                CrawlJob.project_id == project.id,
                CrawlJob.organisation_id == project.organisation_id,
                CrawlJob.status == CrawlStatus.COMPLETED,
            )
            .order_by(CrawlJob.created_at.desc())
            .limit(1)
        )
    config = await build_config(session, project)
    job = CrawlJob(
        organisation_id=project.organisation_id,
        project_id=project.id,
        requested_by_id=access.user.id,
        status=CrawlStatus.QUEUED,
        incremental=previous_id is not None,
        previous_crawl_id=previous_id,
        config=config.model_dump(),
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A crawl is already queued or running for this project") from exc
    audit.record(
        session,
        action="crawl.started",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="crawl",
        target_id=job.id,
        details={"project_id": str(project.id), "incremental": job.incremental},
    )
    await session.commit()
    await session.refresh(job)
    return job


async def cancel(session: AsyncSession, access: CrawlAccess, meta: RequestMeta) -> CrawlJob:
    job = await session.get(CrawlJob, access.crawl.id, with_for_update=True)
    if job is None or job.status not in ACTIVE_STATUSES:
        raise ConflictError("Only queued or running crawls can be cancelled")
    if job.status == CrawlStatus.QUEUED:
        job.status = CrawlStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
    else:
        job.status = CrawlStatus.CANCELLING
    audit.record(
        session,
        action="crawl.cancelled",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=job.organisation_id,
        target_type="crawl",
        target_id=job.id,
    )
    await session.commit()
    await session.refresh(job)
    return job


async def cancel_active_for_project(session: AsyncSession, project: Project) -> None:
    """Called when a project is deleted; the caller commits."""
    rows = await session.scalars(
        select(CrawlJob).where(
            CrawlJob.project_id == project.id, CrawlJob.status.in_(ACTIVE_STATUSES)
        )
    )
    for job in rows:
        if job.status == CrawlStatus.QUEUED:
            job.status = CrawlStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
        else:
            job.status = CrawlStatus.CANCELLING


async def list_crawls(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    params: PageParams,
    project_id: uuid.UUID | None,
    status: CrawlStatus | None,
    analysed: bool | None = None,
) -> tuple[list[CrawlJobOut], int]:
    query = (
        select(CrawlJob, Project.name)
        .join(Project, Project.id == CrawlJob.project_id)
        .where(CrawlJob.organisation_id == organisation_id, Project.deleted_at.is_(None))
    )
    if project_id:
        query = query.where(CrawlJob.project_id == project_id)
    if status:
        query = query.where(CrawlJob.status == status)
    if analysed is not None:
        completed = CrawlJob.analysis_status == AnalysisStatus.COMPLETED
        query = query.where(completed if analysed else ~completed)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(
        query.order_by(CrawlJob.created_at.desc()).offset(params.offset).limit(params.page_size)
    )
    return [to_out(job, name) for job, name in rows.all()], total


def _page_query(crawl: CrawlJob) -> Select[CrawlPage]:
    return select(CrawlPage).where(
        CrawlPage.crawl_job_id == crawl.id, CrawlPage.organisation_id == crawl.organisation_id
    )


async def list_pages(
    session: AsyncSession,
    crawl: CrawlJob,
    params: PageParams,
    *,
    status_class: StatusClass | None,
    fetch_status: FetchStatus | None,
    q: str | None,
    in_sitemap: bool | None,
    orphan: bool | None,
    noindex: bool | None,
    sort: PageSort,
    order: str,
) -> tuple[list[CrawlPage], int]:
    query = _page_query(crawl)
    if status_class == "none":
        query = query.where(CrawlPage.status_code.is_(None))
    elif status_class:
        low = int(status_class[0]) * 100
        query = query.where(CrawlPage.status_code >= low, CrawlPage.status_code < low + 100)
    if fetch_status:
        query = query.where(CrawlPage.fetch_status == fetch_status)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        query = query.where(
            or_(
                CrawlPage.url.ilike(pattern, escape="\\"),
                CrawlPage.title.ilike(pattern, escape="\\"),
            )
        )
    if in_sitemap is not None:
        query = query.where(CrawlPage.in_sitemap.is_(in_sitemap))
    if orphan is not None:
        query = query.where(CrawlPage.is_orphan.is_(orphan))
    if noindex is not None:
        query = query.where(CrawlPage.is_noindex.is_(noindex))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    column = getattr(CrawlPage, sort)
    ordered = column.asc().nulls_last() if order == "asc" else column.desc().nulls_last()
    rows = await session.scalars(
        query.order_by(ordered, CrawlPage.url).offset(params.offset).limit(params.page_size)
    )
    return list(rows), total


async def page_detail(session: AsyncSession, crawl: CrawlJob, page: CrawlPage) -> CrawlPageDetail:
    detail = CrawlPageDetail.model_validate(page)
    target = aliased(CrawlPage)
    out_rows = await session.execute(
        select(CrawlLink, target.status_code)
        .outerjoin(target, target.id == CrawlLink.target_page_id)
        .where(CrawlLink.source_page_id == page.id, CrawlLink.crawl_job_id == crawl.id)
        .order_by(CrawlLink.target_url)
        .limit(500)
    )
    detail.outlinks = [
        LinkOut(
            url=link.target_url,
            anchor_text=link.anchor_text,
            nofollow=link.nofollow,
            is_internal=link.is_internal,
            page_id=link.target_page_id,
            status_code=status,
        )
        for link, status in out_rows.all()
    ]
    source = aliased(CrawlPage)
    in_rows = await session.execute(
        select(CrawlLink, source.url, source.status_code)
        .join(source, source.id == CrawlLink.source_page_id)
        .where(CrawlLink.target_page_id == page.id, CrawlLink.crawl_job_id == crawl.id)
        .order_by(source.url)
        .limit(500)
    )
    detail.inlinks = [
        LinkOut(
            url=url,
            anchor_text=link.anchor_text,
            nofollow=link.nofollow,
            is_internal=True,
            page_id=link.source_page_id,
            status_code=status,
        )
        for link, url, status in in_rows.all()
    ]
    return detail


def _broken_query(crawl: CrawlJob) -> Select[CrawlLink, str, CrawlPage]:
    source = aliased(CrawlPage)
    target = aliased(CrawlPage)
    return (
        select(CrawlLink, source.url, target)
        .join(source, source.id == CrawlLink.source_page_id)
        .join(target, target.id == CrawlLink.target_page_id)
        .where(
            CrawlLink.crawl_job_id == crawl.id,
            CrawlLink.organisation_id == crawl.organisation_id,
            CrawlLink.is_internal.is_(True),
            or_(target.status_code >= 400, target.fetch_status.in_(FAILED_FETCHES)),
        )
    )


async def broken_links(
    session: AsyncSession, crawl: CrawlJob, params: PageParams
) -> tuple[list[BrokenLinkOut], int]:
    query = _broken_query(crawl)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(
        query.order_by(CrawlLink.target_url).offset(params.offset).limit(params.page_size)
    )
    return [
        BrokenLinkOut(
            source_page_id=link.source_page_id,
            source_url=source_url,
            target_page_id=target.id,
            target_url=link.target_url,
            anchor_text=link.anchor_text,
            status_code=target.status_code,
            fetch_status=target.fetch_status,
        )
        for link, source_url, target in rows.all()
    ], total


async def summary(session: AsyncSession, crawl: CrawlJob) -> CrawlSummary:
    base = _page_query(crawl).subquery()
    status_class = func.coalesce(cast(base.c.status_code // 100, String) + "xx", "none")
    classes = dict(
        (await session.execute(select(status_class, func.count()).group_by(status_class))).all()
    )
    fetches: dict[Any, int] = dict(
        (
            await session.execute(
                select(base.c.fetch_status, func.count()).group_by(base.c.fetch_status)
            )
        ).all()
    )
    stats = (
        await session.execute(
            select(
                func.count(),
                func.avg(base.c.response_time_ms),
                func.max(base.c.response_time_ms),
                func.count().filter(base.c.is_noindex.is_(True)),
                func.count().filter(base.c.in_sitemap.is_(True)),
                func.count().filter(base.c.is_orphan.is_(True)),
                func.count().filter(base.c.status_code.between(300, 399)),
            )
        )
    ).one()
    broken = (
        await session.scalar(select(func.count()).select_from(_broken_query(crawl).subquery())) or 0
    )
    dup_rows = await session.execute(
        select(base.c.content_hash, func.array_agg(base.c.url))
        .where(base.c.content_hash.is_not(None))
        .group_by(base.c.content_hash)
        .having(func.count() > 1)
        .limit(50)
    )
    return CrawlSummary(
        pages_total=stats[0],
        status_classes={str(k): v for k, v in classes.items()},
        fetch_statuses={str(getattr(k, "value", k)): v for k, v in fetches.items()},
        average_response_time_ms=round(stats[1]) if stats[1] is not None else None,
        slowest_response_time_ms=stats[2],
        noindex_pages=stats[3],
        pages_in_sitemap=stats[4],
        orphan_pages=stats[5],
        broken_internal_links=broken,
        redirects=stats[6],
        duplicate_content_groups=[
            DuplicateGroup(content_hash=h, urls=sorted(urls)) for h, urls in dup_rows.all()
        ],
    )
