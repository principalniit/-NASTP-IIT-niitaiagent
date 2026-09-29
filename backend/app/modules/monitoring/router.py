from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.request_context import get_request_meta
from app.modules.monitoring import service
from app.modules.monitoring.schemas import ScheduleIn, ScheduleOut
from app.modules.organisations.dependencies import ProjectAccess, require_project
from app.modules.organisations.permissions import Permission

router = APIRouter(tags=["monitoring"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/projects/{project_id}/schedule", response_model=ScheduleOut)
async def get_schedule(
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))],
) -> ScheduleOut:
    return await service.get_schedule(session, access.project)


@router.put("/projects/{project_id}/schedule", response_model=ScheduleOut)
async def save_schedule(
    body: ScheduleIn,
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECT_SETTINGS_UPDATE))],
) -> ScheduleOut:
    return await service.save_schedule(session, access, body, get_request_meta(request))
