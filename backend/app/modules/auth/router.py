from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import ForbiddenError
from app.core.request_context import get_request_meta
from app.modules.auth import service
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MembershipOut,
    MeResponse,
    TokenResponse,
)
from app.modules.organisations.models import Organisation, OrganisationMember
from app.modules.organisations.permissions import permissions_for
from app.modules.users.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "niit_refresh"
COOKIE_PATH = "/api/v1/auth"
Session = Annotated[AsyncSession, Depends(get_session)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )


def _require_xhr(x_requested_with: str | None) -> None:
    # Cross-site HTML forms cannot set custom headers, so this blocks CSRF on cookie auth.
    if x_requested_with != "XMLHttpRequest":
        raise ForbiddenError("Missing X-Requested-With header")


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, session: Session
) -> TokenResponse:
    tokens = await service.login(session, body.email, body.password, get_request_meta(request))
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Session,
    niit_refresh: Annotated[str | None, Cookie()] = None,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    _require_xhr(x_requested_with)
    tokens = await service.refresh(session, niit_refresh, get_request_meta(request))
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    session: Session,
    niit_refresh: Annotated[str | None, Cookie()] = None,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> Response:
    _require_xhr(x_requested_with)
    await service.logout(session, niit_refresh, get_request_meta(request))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, session: Session) -> MeResponse:
    rows = await session.execute(
        select(Organisation, OrganisationMember.role)
        .join(OrganisationMember, OrganisationMember.organisation_id == Organisation.id)
        .where(OrganisationMember.user_id == user.id, Organisation.is_active.is_(True))
        .order_by(Organisation.name)
    )
    memberships = [
        MembershipOut(
            organisation_id=org.id,
            organisation_name=org.name,
            organisation_slug=org.slug,
            role=role,
            permissions=permissions_for(role),
        )
        for org, role in rows.all()
    ]
    return MeResponse(user=UserOut.model_validate(user), memberships=memberships)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest, request: Request, user: CurrentUser, session: Session
) -> Response:
    await service.change_password(
        session, user, body.current_password, body.new_password, get_request_meta(request)
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response
