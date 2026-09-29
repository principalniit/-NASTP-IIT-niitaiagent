import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, RateLimitedError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.ai.models import AIAnalysis, AIKind, AIStatus, SeoRecommendation
from app.modules.ai.provider import build_provider, choose_provider
from app.modules.ai.schemas import AIRequest, AIStatusOut
from app.modules.audit_logs import service as audit
from app.modules.crawler.models import CrawlPage
from app.modules.crawler.urls import normalise_url
from app.modules.drafts.models import ContentDraft
from app.modules.organisations.dependencies import ProjectAccess
from app.modules.organisations.models import Organisation
from app.modules.organisations.permissions import Permission, role_has
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.plans.service import enforce
from app.modules.seo.models import SeoIssue
from app.modules.seo.service import latest_analysed_crawl

PERMISSION_FOR_KIND = {
    AIKind.MANAGEMENT_SUMMARY: Permission.REPORTS_GENERATE,
    AIKind.QUESTION: Permission.ISSUES_TRIAGE,
    AIKind.ISSUE_EXPLANATION: Permission.ISSUES_TRIAGE,
    AIKind.PAGE_PLAN: Permission.ISSUES_TRIAGE,
    AIKind.METADATA_DRAFT: Permission.DRAFTS_CREATE,
    AIKind.CONTENT_OUTLINE: Permission.DRAFTS_CREATE,
}


async def ai_status(org: Organisation) -> AIStatusOut:
    choice = choose_provider(OrganisationSettings.model_validate(org.settings))
    if not choice.enabled or choice.model is None:
        return AIStatusOut(
            enabled=False,
            provider=choice.provider,
            model=choice.model,
            status="disabled",
            detail=choice.reason,
        )
    health = await build_provider(choice).health()
    return AIStatusOut(
        enabled=True,
        provider="ollama",
        model=choice.model,
        status=health.status,
        detail=health.detail,
    )


async def request_analysis(
    session: AsyncSession, access: ProjectAccess, body: AIRequest, meta: RequestMeta
) -> AIAnalysis:
    if not role_has(access.role, PERMISSION_FOR_KIND[body.kind]):
        raise ForbiddenError("Your role does not permit this AI task")
    project = access.project
    org = await session.get(Organisation, project.organisation_id)
    if org is None:
        raise NotFoundError("Project not found")
    choice = choose_provider(OrganisationSettings.model_validate(org.settings))
    if not choice.enabled:
        raise ConflictError(choice.reason or "AI is not available", code="ai_disabled")
    active = (
        await session.scalar(
            select(func.count()).where(
                AIAnalysis.organisation_id == org.id,
                AIAnalysis.status.in_([AIStatus.QUEUED, AIStatus.RUNNING]),
            )
        )
        or 0
    )
    await enforce(session, org.id, "ai_tasks_per_day")
    if active >= get_settings().ai_max_active_jobs_per_org:
        raise RateLimitedError(
            "Too many AI tasks are already queued for this organisation. Try again shortly."
        )

    subject_type, subject_id = "project", None
    params: dict[str, str] = {}
    crawl = await latest_analysed_crawl(session, project.id, org.id)
    if body.kind != AIKind.QUESTION and crawl is None:
        raise ConflictError(
            "Crawl and analyse this project before using the AI assistant", code="not_analysed"
        )
    if body.kind == AIKind.ISSUE_EXPLANATION:
        issue = await session.scalar(
            select(SeoIssue).where(
                SeoIssue.id == body.issue_id,
                SeoIssue.project_id == project.id,
                SeoIssue.organisation_id == org.id,
            )
        )
        if issue is None:
            raise NotFoundError("Issue not found")
        subject_type, subject_id = "issue", str(issue.id)
    elif body.kind in (AIKind.PAGE_PLAN, AIKind.METADATA_DRAFT, AIKind.CONTENT_OUTLINE):
        url = normalise_url(body.page_url or "", project.root_url)
        page = None
        if url and crawl is not None:
            page = await session.scalar(
                select(CrawlPage).where(
                    CrawlPage.crawl_job_id == crawl.id,
                    CrawlPage.organisation_id == org.id,
                    CrawlPage.url == url,
                )
            )
        if page is None or not page.analysable_hint():
            raise NotFoundError("That page is not an HTML page in the latest analysed crawl")
        subject_type, subject_id = "page", str(page.id)
        params = {"page_url": page.url}
        if body.goal:
            params["goal"] = body.goal
    elif body.kind == AIKind.QUESTION:
        subject_type, params = "question", {"question": body.question or ""}
    analysis = AIAnalysis(
        organisation_id=org.id,
        project_id=project.id,
        crawl_job_id=crawl.id if crawl else None,
        kind=body.kind,
        status=AIStatus.QUEUED,
        subject_type=subject_type,
        subject_id=subject_id,
        params=params,
        requested_by_id=access.user.id,
        provider=choice.provider,
        model=choice.model,
    )
    session.add(analysis)
    await session.flush()
    audit.record(
        session,
        action="ai.requested",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org.id,
        target_type="ai_analysis",
        target_id=analysis.id,
        details={"kind": body.kind.value},
    )
    await session.commit()
    await session.refresh(analysis)
    return analysis


async def list_analyses(
    session: AsyncSession,
    project_id: uuid.UUID,
    organisation_id: uuid.UUID,
    params: PageParams,
    kind: AIKind | None,
    *,
    subject_id: str | None = None,
    page_url: str | None = None,
) -> tuple[list[AIAnalysis], int]:
    query = select(AIAnalysis).where(
        AIAnalysis.project_id == project_id, AIAnalysis.organisation_id == organisation_id
    )
    if kind:
        query = query.where(AIAnalysis.kind == kind)
    if subject_id:
        query = query.where(AIAnalysis.subject_id == subject_id)
    if page_url:
        query = query.where(AIAnalysis.params["page_url"].astext == page_url)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(AIAnalysis.created_at.desc()).offset(params.offset).limit(params.page_size)
    )
    return list(rows), total


async def draft_ids(session: AsyncSession, analysis: AIAnalysis) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(ContentDraft.id).where(
                ContentDraft.ai_analysis_id == analysis.id,
                ContentDraft.organisation_id == analysis.organisation_id,
            )
        )
    )


async def list_recommendations(
    session: AsyncSession,
    project_id: uuid.UUID,
    organisation_id: uuid.UUID,
    params: PageParams,
    status: str | None,
) -> tuple[list[SeoRecommendation], int]:
    query = select(SeoRecommendation).where(
        SeoRecommendation.project_id == project_id,
        SeoRecommendation.organisation_id == organisation_id,
    )
    if status:
        query = query.where(SeoRecommendation.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(SeoRecommendation.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    return list(rows), total
