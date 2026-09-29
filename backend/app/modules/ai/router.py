import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.ai import service
from app.modules.ai.models import AIKind, RecommendationStatus
from app.modules.ai.schemas import (
    AIAnalysisOut,
    AIAnalysisSummary,
    AIRequest,
    AIStatusOut,
    RecommendationOut,
    RecommendationUpdate,
)
from app.modules.audit_logs import service as audit
from app.modules.organisations.dependencies import (
    AnalysisAccess,
    OrgAccess,
    ProjectAccess,
    RecommendationAccess,
    require_ai_analysis,
    require_org,
    require_project,
    require_recommendation,
)
from app.modules.organisations.permissions import Permission
from app.modules.seo.compare import compare_crawls

router = APIRouter(tags=["ai"])
Session = Annotated[AsyncSession, Depends(get_session)]
Paging = Annotated[PageParams, Depends(page_params)]
ReadProject = Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))]


@router.get("/organisations/{organisation_id}/ai/status", response_model=AIStatusOut)
async def ai_status(
    access: Annotated[OrgAccess, Depends(require_org(Permission.ORG_READ))],
) -> AIStatusOut:
    return await service.ai_status(access.organisation)


@router.post(
    "/projects/{project_id}/ai/analyses",
    response_model=AIAnalysisSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_analysis(
    body: AIRequest, request: Request, session: Session, access: ReadProject
) -> AIAnalysisSummary:
    analysis = await service.request_analysis(session, access, body, get_request_meta(request))
    return AIAnalysisSummary.model_validate(analysis)


@router.get("/projects/{project_id}/ai/analyses", response_model=Page[AIAnalysisSummary])
async def list_analyses(
    session: Session,
    paging: Paging,
    access: ReadProject,
    kind: AIKind | None = None,
    subject_id: Annotated[str | None, Query(max_length=64)] = None,
    page_url: Annotated[str | None, Query(max_length=2048)] = None,
) -> Page[AIAnalysisSummary]:
    items, total = await service.list_analyses(
        session,
        access.project.id,
        access.project.organisation_id,
        paging,
        kind,
        subject_id=subject_id,
        page_url=page_url,
    )
    return Page(
        items=[AIAnalysisSummary.model_validate(i) for i in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/ai-analyses/{analysis_id}", response_model=AIAnalysisOut)
async def get_analysis(
    session: Session,
    access: Annotated[AnalysisAccess, Depends(require_ai_analysis(Permission.PROJECTS_READ))],
) -> AIAnalysisOut:
    out = AIAnalysisOut.model_validate(access.analysis)
    out.draft_ids = await service.draft_ids(session, access.analysis)
    return out


@router.get("/projects/{project_id}/recommendations", response_model=Page[RecommendationOut])
async def list_recommendations(
    session: Session,
    paging: Paging,
    access: ReadProject,
    status_filter: RecommendationStatus | None = None,
) -> Page[RecommendationOut]:
    items, total = await service.list_recommendations(
        session,
        access.project.id,
        access.project.organisation_id,
        paging,
        status_filter.value if status_filter else None,
    )
    return Page(
        items=[RecommendationOut.model_validate(i) for i in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.patch("/recommendations/{recommendation_id}", response_model=RecommendationOut)
async def update_recommendation(
    body: RecommendationUpdate,
    request: Request,
    session: Session,
    access: Annotated[
        RecommendationAccess, Depends(require_recommendation(Permission.ISSUES_TRIAGE))
    ],
) -> RecommendationOut:
    rec = access.recommendation
    rec.status = body.status
    audit.record(
        session,
        action="recommendation.updated",
        actor_id=access.user.id,
        meta=get_request_meta(request),
        organisation_id=rec.organisation_id,
        target_type="seo_recommendation",
        target_id=rec.id,
        details={"status": body.status.value},
    )
    await session.commit()
    await session.refresh(rec)
    return RecommendationOut.model_validate(rec)


@router.get("/projects/{project_id}/compare")
async def compare(
    session: Session,
    access: ReadProject,
    from_crawl: uuid.UUID | None = None,
    to_crawl: uuid.UUID | None = None,
) -> dict[str, Any]:
    return await compare_crawls(
        session, access.project.id, access.project.organisation_id, from_crawl, to_crawl
    )
