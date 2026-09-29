import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.crawler import service
from app.modules.crawler.models import CrawlPage, CrawlStatus, FetchStatus
from app.modules.crawler.schemas import (
    BrokenLinkOut,
    CrawlJobOut,
    CrawlPageDetail,
    CrawlPageRow,
    CrawlStartRequest,
    CrawlSummary,
    PageSort,
    StatusClass,
)
from app.modules.organisations.dependencies import (
    CrawlAccess,
    OrgAccess,
    ProjectAccess,
    require_crawl,
    require_org,
    require_project,
)
from app.modules.organisations.permissions import Permission

router = APIRouter(tags=["crawls"])
Session = Annotated[AsyncSession, Depends(get_session)]
Paging = Annotated[PageParams, Depends(page_params)]
ReadCrawl = Annotated[CrawlAccess, Depends(require_crawl(Permission.PROJECTS_READ))]


@router.post(
    "/projects/{project_id}/crawls", response_model=CrawlJobOut, status_code=status.HTTP_201_CREATED
)
async def start_crawl(
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.CRAWLS_START))],
    body: CrawlStartRequest | None = None,
) -> CrawlJobOut:
    job = await service.start(
        session, access, (body or CrawlStartRequest()).incremental, get_request_meta(request)
    )
    return service.to_out(job, access.project.name)


@router.get("/organisations/{organisation_id}/crawls", response_model=Page[CrawlJobOut])
async def list_crawls(
    session: Session,
    paging: Paging,
    access: Annotated[OrgAccess, Depends(require_org(Permission.PROJECTS_READ))],
    project_id: uuid.UUID | None = None,
    status_filter: Annotated[CrawlStatus | None, Query(alias="status")] = None,
    analysed: bool | None = None,
) -> Page[CrawlJobOut]:
    items, total = await service.list_crawls(
        session, access.organisation.id, paging, project_id, status_filter, analysed
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.get("/crawls/{crawl_id}", response_model=CrawlJobOut)
async def get_crawl(access: ReadCrawl) -> CrawlJobOut:
    return service.to_out(access.crawl, access.project.name)


@router.post("/crawls/{crawl_id}/cancel", response_model=CrawlJobOut)
async def cancel_crawl(
    request: Request,
    session: Session,
    access: Annotated[CrawlAccess, Depends(require_crawl(Permission.CRAWLS_START))],
) -> CrawlJobOut:
    job = await service.cancel(session, access, get_request_meta(request))
    return service.to_out(job, access.project.name)


@router.get("/crawls/{crawl_id}/summary", response_model=CrawlSummary)
async def crawl_summary(session: Session, access: ReadCrawl) -> CrawlSummary:
    return await service.summary(session, access.crawl)


@router.get("/crawls/{crawl_id}/pages", response_model=Page[CrawlPageRow])
async def list_pages(
    session: Session,
    paging: Paging,
    access: ReadCrawl,
    status_class: StatusClass | None = None,
    fetch_status: FetchStatus | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    in_sitemap: bool | None = None,
    orphan: bool | None = None,
    noindex: bool | None = None,
    sort: PageSort = "url",
    order: Literal["asc", "desc"] = "asc",
) -> Page[CrawlPageRow]:
    items, total = await service.list_pages(
        session,
        access.crawl,
        paging,
        status_class=status_class,
        fetch_status=fetch_status,
        q=q,
        in_sitemap=in_sitemap,
        orphan=orphan,
        noindex=noindex,
        sort=sort,
        order=order,
    )
    return Page(
        items=[CrawlPageRow.model_validate(p) for p in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/crawls/{crawl_id}/pages/{page_id}", response_model=CrawlPageDetail)
async def get_page(page_id: uuid.UUID, session: Session, access: ReadCrawl) -> CrawlPageDetail:
    page = await session.scalar(
        select(CrawlPage).where(
            CrawlPage.id == page_id,
            CrawlPage.crawl_job_id == access.crawl.id,
            CrawlPage.organisation_id == access.crawl.organisation_id,
        )
    )
    if page is None:
        raise NotFoundError("Page not found")
    return await service.page_detail(session, access.crawl, page)


@router.get("/crawls/{crawl_id}/broken-links", response_model=Page[BrokenLinkOut])
async def list_broken_links(
    session: Session, paging: Paging, access: ReadCrawl
) -> Page[BrokenLinkOut]:
    items, total = await service.broken_links(session, access.crawl, paging)
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)
