import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.request_context import get_request_meta
from app.modules.auth.dependencies import CurrentUser
from app.modules.invitations import service
from app.modules.invitations.schemas import (
    Accepted,
    AcceptNew,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    InvitationPreview,
    TokenBody,
)
from app.modules.organisations.dependencies import OrgAccess, require_org
from app.modules.organisations.permissions import Permission

router = APIRouter(tags=["invitations"])
Session = Annotated[AsyncSession, Depends(get_session)]
Managers = Annotated[OrgAccess, Depends(require_org(Permission.MEMBERS_MANAGE))]


@router.post(
    "/organisations/{organisation_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    body: InvitationCreate, request: Request, session: Session, access: Managers
) -> InvitationCreated:
    invitation, link, sent = await service.create(
        session, access, body.email, body.role, get_request_meta(request)
    )
    return InvitationCreated(
        invitation=InvitationOut.model_validate(invitation), invite_url=link, email_sent=sent
    )


@router.get("/organisations/{organisation_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(session: Session, access: Managers) -> list[InvitationOut]:
    rows = await service.list_pending(session, access.organisation.id)
    return [InvitationOut.model_validate(r) for r in rows]


@router.delete(
    "/organisations/{organisation_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    invitation_id: uuid.UUID, request: Request, session: Session, access: Managers
) -> Response:
    await service.revoke(session, access, invitation_id, get_request_meta(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# The token travels in the request body, never the URL, so it stays out of access logs.
@router.post("/invitations/lookup", response_model=InvitationPreview)
async def lookup_invitation(body: TokenBody, session: Session) -> InvitationPreview:
    invitation, org, account_exists = await service.lookup(session, body.token)
    return InvitationPreview(
        organisation_name=org.name,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        account_exists=account_exists,
    )


@router.post("/invitations/accept-new", response_model=Accepted)
async def accept_with_new_account(body: AcceptNew, request: Request, session: Session) -> Accepted:
    invitation = await service.accept_new(
        session, body.token, body.full_name, body.password, get_request_meta(request)
    )
    return Accepted(organisation_id=invitation.organisation_id, email=invitation.email)


@router.post("/invitations/accept", response_model=Accepted)
async def accept_as_current_user(
    body: TokenBody, request: Request, user: CurrentUser, session: Session
) -> Accepted:
    invitation = await service.accept_existing(session, user, body.token, get_request_meta(request))
    return Accepted(organisation_id=invitation.organisation_id, email=invitation.email)
