from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.organisations.dependencies import (
    OrgAccess,
    ProjectAccess,
    require_org,
    require_project,
)
from app.modules.organisations.permissions import Permission
from app.modules.projects import service
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectSettingsData,
    ProjectSettingsOut,
    ProjectSort,
    ProjectUpdate,
    SortOrder,
)

router = APIRouter(tags=["projects"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/organisations/{organisation_id}/projects", response_model=Page[ProjectOut])
async def list_projects(
    session: Session,
    paging: Annotated[PageParams, Depends(page_params)],
    access: Annotated[OrgAccess, Depends(require_org(Permission.PROJECTS_READ))],
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: ProjectSort = "name",
    order: SortOrder = "asc",
) -> Page[ProjectOut]:
    items, total = await service.list_projects(
        session, access.organisation.id, paging, q, sort, order
    )
    return Page(
        items=[ProjectOut.model_validate(p) for p in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/organisations/{organisation_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreate,
    request: Request,
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.PROJECTS_CREATE))],
) -> ProjectOut:
    project = await service.create(session, access, body, get_request_meta(request))
    return ProjectOut.model_validate(project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))],
) -> ProjectOut:
    return ProjectOut.model_validate(access.project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    body: ProjectUpdate,
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_UPDATE))],
) -> ProjectOut:
    project = await service.update(session, access, body, get_request_meta(request))
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_DELETE))],
) -> Response:
    await service.soft_delete(session, access, get_request_meta(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/settings", response_model=ProjectSettingsOut)
async def get_project_settings(
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))],
) -> ProjectSettingsOut:
    row = await service.get_settings_row(session, access.project)
    return ProjectSettingsOut(
        project_id=row.project_id,
        settings=ProjectSettingsData.model_validate(row.settings),
        updated_at=row.updated_at,
    )


@router.put("/projects/{project_id}/settings", response_model=ProjectSettingsOut)
async def update_project_settings(
    body: ProjectSettingsData,
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECT_SETTINGS_UPDATE))],
) -> ProjectSettingsOut:
    row = await service.update_settings(session, access, body, get_request_meta(request))
    return ProjectSettingsOut(
        project_id=row.project_id,
        settings=ProjectSettingsData.model_validate(row.settings),
        updated_at=row.updated_at,
    )
