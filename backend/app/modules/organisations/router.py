import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ForbiddenError
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.audit_logs import service as audit_service
from app.modules.audit_logs.schemas import AuditLogOut
from app.modules.auth.dependencies import CurrentUser
from app.modules.organisations import service
from app.modules.organisations.dependencies import OrgAccess, require_org
from app.modules.organisations.models import OrgRole
from app.modules.organisations.permissions import Permission
from app.modules.organisations.schemas import (
    MemberCreate,
    MemberOut,
    MemberUpdate,
    OrganisationCreate,
    OrganisationOut,
    OrganisationUpdate,
)

router = APIRouter(prefix="/organisations", tags=["organisations"])
Session = Annotated[AsyncSession, Depends(get_session)]
Paging = Annotated[PageParams, Depends(page_params)]


@router.get("", response_model=Page[OrganisationOut])
async def list_organisations(
    user: CurrentUser, session: Session, paging: Paging
) -> Page[OrganisationOut]:
    items, total = await service.list_for_user(session, user, paging)
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post("", response_model=OrganisationOut, status_code=status.HTTP_201_CREATED)
async def create_organisation(
    body: OrganisationCreate, request: Request, user: CurrentUser, session: Session
) -> OrganisationOut:
    if not user.is_platform_admin:
        raise ForbiddenError("Only platform administrators can create organisations")
    org = await service.create(session, user, body, get_request_meta(request))
    return service.to_out(org, OrgRole.OWNER, user)


@router.get("/{organisation_id}", response_model=OrganisationOut)
async def get_organisation(
    access: Annotated[OrgAccess, Depends(require_org(Permission.ORG_READ))],
) -> OrganisationOut:
    return service.to_out(access.organisation, access.role, access.user)


@router.patch("/{organisation_id}", response_model=OrganisationOut)
async def update_organisation(
    body: OrganisationUpdate,
    request: Request,
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.ORG_UPDATE))],
) -> OrganisationOut:
    org = await service.update(session, access, body, get_request_meta(request))
    return service.to_out(org, access.role, access.user)


@router.get("/{organisation_id}/members", response_model=Page[MemberOut])
async def list_members(
    session: Session,
    paging: Paging,
    access: Annotated[OrgAccess, Depends(require_org(Permission.MEMBERS_READ))],
) -> Page[MemberOut]:
    items, total = await service.list_members(session, access.organisation.id, paging)
    return Page(
        items=[MemberOut.model_validate(m) for m in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/{organisation_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED
)
async def add_member(
    body: MemberCreate,
    request: Request,
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.MEMBERS_MANAGE))],
) -> MemberOut:
    member = await service.add_member(session, access, body, get_request_meta(request))
    return MemberOut.model_validate(member)


@router.patch("/{organisation_id}/members/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    request: Request,
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.MEMBERS_MANAGE))],
) -> MemberOut:
    member = await service.update_member_role(
        session, access, member_id, body.role, get_request_meta(request)
    )
    return MemberOut.model_validate(member)


@router.delete("/{organisation_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID,
    request: Request,
    session: Session,
    access: Annotated[OrgAccess, Depends(require_org(Permission.MEMBERS_MANAGE))],
) -> Response:
    await service.remove_member(session, access, member_id, get_request_meta(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{organisation_id}/audit-logs", response_model=Page[AuditLogOut])
async def list_audit_logs(
    session: Session,
    paging: Paging,
    access: Annotated[OrgAccess, Depends(require_org(Permission.AUDIT_READ))],
    action: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[AuditLogOut]:
    items, total = await audit_service.list_for_organisation(
        session, access.organisation.id, paging, action
    )
    return Page(
        items=[AuditLogOut.model_validate(i) for i in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )
