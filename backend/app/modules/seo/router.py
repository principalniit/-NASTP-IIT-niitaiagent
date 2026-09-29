from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.auth.dependencies import CurrentUser
from app.modules.crawler import service as crawl_service
from app.modules.crawler.schemas import CrawlJobOut
from app.modules.organisations.dependencies import (
    CrawlAccess,
    IssueAccess,
    ProjectAccess,
    require_crawl,
    require_issue,
    require_project,
)
from app.modules.organisations.permissions import Permission
from app.modules.seo import service
from app.modules.seo.models import Category, ResolutionStatus, Severity
from app.modules.seo.rules import rule_catalogue
from app.modules.seo.schemas import (
    IssueOut,
    IssueSort,
    IssueSummary,
    IssueTriage,
    LinkRecommendationOut,
    SchemaFindingOut,
    ScoreOut,
    ScorePoint,
)

router = APIRouter(tags=["seo"])
Session = Annotated[AsyncSession, Depends(get_session)]
Paging = Annotated[PageParams, Depends(page_params)]
ReadProject = Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))]
ReadCrawl = Annotated[CrawlAccess, Depends(require_crawl(Permission.PROJECTS_READ))]


@router.get("/seo-rules")
async def list_rules(_: CurrentUser) -> list[dict[str, Any]]:
    """Every rule the engine applies, with its default severity and recommendation."""
    return rule_catalogue()


@router.get("/projects/{project_id}/issues", response_model=Page[IssueOut])
async def list_issues(
    session: Session,
    paging: Paging,
    access: ReadProject,
    status_filter: Annotated[
        ResolutionStatus | None, Query(alias="status")
    ] = ResolutionStatus.OPEN,
    all_statuses: bool = False,
    severity: Severity | None = None,
    category: Category | None = None,
    rule_id: Annotated[str | None, Query(max_length=80)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: IssueSort = "priority",
    order: Literal["asc", "desc"] = "desc",
) -> Page[IssueOut]:
    items, total = await service.list_issues(
        session,
        access.project.id,
        access.project.organisation_id,
        paging,
        status=None if all_statuses else status_filter,
        severity=severity,
        category=category,
        rule_id=rule_id,
        q=q,
        sort=sort,
        order=order,
    )
    return Page(
        items=[IssueOut.model_validate(i) for i in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/projects/{project_id}/issues/summary", response_model=IssueSummary)
async def issue_summary(session: Session, access: ReadProject) -> IssueSummary:
    return await service.summary(session, access.project.id, access.project.organisation_id)


@router.get("/projects/{project_id}/scores", response_model=list[ScorePoint])
async def score_history(session: Session, access: ReadProject) -> list[ScorePoint]:
    rows = await service.score_history(session, access.project.id, access.project.organisation_id)
    return [ScorePoint.model_validate(r) for r in rows]


@router.get("/issues/{issue_id}", response_model=IssueOut)
async def get_issue(
    access: Annotated[IssueAccess, Depends(require_issue(Permission.PROJECTS_READ))],
) -> IssueOut:
    return IssueOut.model_validate(access.issue)


@router.patch("/issues/{issue_id}", response_model=IssueOut)
async def triage_issue(
    body: IssueTriage,
    request: Request,
    session: Session,
    access: Annotated[IssueAccess, Depends(require_issue(Permission.ISSUES_TRIAGE))],
) -> IssueOut:
    issue = await service.triage(session, access, body, get_request_meta(request))
    return IssueOut.model_validate(issue)


@router.get("/crawls/{crawl_id}/score", response_model=ScoreOut)
async def crawl_score(session: Session, access: ReadCrawl) -> ScoreOut:
    return ScoreOut.model_validate(await service.get_score(session, access.crawl))


@router.get("/crawls/{crawl_id}/schema-findings", response_model=Page[SchemaFindingOut])
async def schema_findings(
    session: Session, paging: Paging, access: ReadCrawl, invalid_only: bool = False
) -> Page[SchemaFindingOut]:
    items, total = await service.schema_findings(session, access.crawl, paging, invalid_only)
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.get("/crawls/{crawl_id}/link-recommendations", response_model=Page[LinkRecommendationOut])
async def link_recommendations(
    session: Session, paging: Paging, access: ReadCrawl
) -> Page[LinkRecommendationOut]:
    items, total = await service.link_recommendations(session, access.crawl, paging)
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/crawls/{crawl_id}/analyse", response_model=CrawlJobOut, status_code=status.HTTP_202_ACCEPTED
)
async def request_analysis(
    request: Request,
    session: Session,
    access: Annotated[CrawlAccess, Depends(require_crawl(Permission.CRAWLS_START))],
) -> CrawlJobOut:
    job = await service.request_analysis(session, access, get_request_meta(request))
    return crawl_service.to_out(job, access.project.name)
