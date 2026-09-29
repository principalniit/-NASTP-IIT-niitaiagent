import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ForbiddenError, NotFoundError
from app.core.request_context import get_request_meta
from app.modules.auth.dependencies import CurrentUser
from app.modules.organisations.dependencies import OrgAccess, get_membership, require_org
from app.modules.organisations.models import Organisation
from app.modules.organisations.permissions import Permission
from app.modules.plans import service
from app.modules.plans.schemas import PlanAssignment, PlanCreate, PlanOut, PlanUpdate, UsageOut
from app.modules.users.models import User

router = APIRouter(tags=["plans"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _platform_admin(user: User) -> None:
    if not user.is_platform_admin:
        raise ForbiddenError("Only platform administrators manage plans")


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(user: CurrentUser, session: Session) -> list[PlanOut]:
    _platform_admin(user)
    return [PlanOut.model_validate(p) for p in await service.list_plans(session)]


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PlanCreate, request: Request, user: CurrentUser, session: Session
) -> PlanOut:
    _platform_admin(user)
    return PlanOut.model_validate(
        await service.create_plan(session, user, body, get_request_meta(request))
    )


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: uuid.UUID, body: PlanUpdate, request: Request, user: CurrentUser, session: Session
) -> PlanOut:
    _platform_admin(user)
    return PlanOut.model_validate(
        await service.update_plan(session, user, plan_id, body, get_request_meta(request))
    )


async def admin_org(
    organisation_id: uuid.UUID, user: CurrentUser, session: Session
) -> Organisation:
    """The organisation, for a platform administrator. Runs before the body is read."""
    org = await session.get(Organisation, organisation_id)
    if org is None:
        raise NotFoundError("Organisation not found")
    if not user.is_platform_admin:
        # Members learn why they cannot; everyone else cannot tell the organisation exists.
        if await get_membership(session, org.id, user.id):
            raise ForbiddenError("Only platform administrators can change an organisation's plan")
        raise NotFoundError("Organisation not found")
    return org


@router.put("/organisations/{organisation_id}/plan", response_model=UsageOut)
async def assign_plan(
    org: Annotated[Organisation, Depends(admin_org)],
    body: PlanAssignment,
    request: Request,
    user: CurrentUser,
    session: Session,
) -> UsageOut:
    org = await service.assign_plan(session, user, org, body.plan_key, get_request_meta(request))
    return await service.usage(session, org)


@router.get("/organisations/{organisation_id}/usage", response_model=UsageOut)
async def usage(
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.ORG_READ))],
) -> UsageOut:
    return await service.usage(session, access.organisation)
