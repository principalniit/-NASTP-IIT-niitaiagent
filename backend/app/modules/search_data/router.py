from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.request_context import get_request_meta
from app.modules.organisations.dependencies import (
    IntegrationAccess,
    ProjectAccess,
    require_integration,
    require_project,
)
from app.modules.organisations.permissions import Permission
from app.modules.search_data import service
from app.modules.search_data.schemas import (
    ConnectionTest,
    PagePerformanceOut,
    PerformanceOut,
    SyncOut,
)

router = APIRouter(tags=["search data"])
Session = Annotated[AsyncSession, Depends(get_session)]
ManageIntegration = Annotated[
    IntegrationAccess, Depends(require_integration(Permission.INTEGRATIONS_MANAGE))
]
ReadProject = Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))]
Days = Annotated[int, Query(ge=7, le=90)]


@router.post("/integrations/{integration_id}/search-console/test", response_model=ConnectionTest)
async def test_connection(session: Session, access: ManageIntegration) -> ConnectionTest:
    """Sign in with the saved key and check the account can read the property."""
    return ConnectionTest(**await service.test_connection(session, access))


@router.post(
    "/integrations/{integration_id}/search-console/syncs",
    response_model=SyncOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_sync(request: Request, session: Session, access: ManageIntegration) -> SyncOut:
    sync = await service.request_sync(session, access, get_request_meta(request))
    return SyncOut.model_validate(sync)


@router.get("/integrations/{integration_id}/search-console/syncs", response_model=list[SyncOut])
async def list_syncs(session: Session, access: ManageIntegration) -> list[SyncOut]:
    return [
        SyncOut.model_validate(s) for s in await service.latest_syncs(session, access.integration)
    ]


@router.get("/projects/{project_id}/search-performance", response_model=PerformanceOut)
async def project_performance(
    session: Session, access: ReadProject, days: Days = 28
) -> PerformanceOut:
    return PerformanceOut(**await service.performance(session, access.project, days))


@router.get("/projects/{project_id}/search-performance/page", response_model=PagePerformanceOut)
async def page_performance(
    session: Session,
    access: ReadProject,
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    days: Days = 28,
) -> PagePerformanceOut:
    return PagePerformanceOut(**await service.page_performance(session, access.project, url, days))
