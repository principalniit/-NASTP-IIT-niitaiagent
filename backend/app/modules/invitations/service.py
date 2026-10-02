"""Invitations: an administrator invites an email address, and the person behind it joins.

Only the token's hash is stored. The raw token travels in the link's fragment
(`/invite#token=...`), which browsers never send to a server or in a Referer header.
Whoever holds the link proves control of it; when email is configured the link goes only
to the invited address, so the invitee proves control of that address too.

An existing account is never attached by an administrator: its owner signs in and accepts,
so nobody can pull an account they do not control into their organisation.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.mailer import send_email
from app.core.request_context import RequestMeta
from app.core.security import hash_token
from app.modules.audit_logs import service as audit
from app.modules.invitations.models import Invitation
from app.modules.organisations.dependencies import OrgAccess
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.plans.service import enforce
from app.modules.users.models import User
from app.modules.users.service import build_user, get_by_email, normalise_email

_INVALID = "This invitation is not valid or has expired"


def _now() -> datetime:
    return datetime.now(UTC)


def invite_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/invite#token={token}"


def _is_pending(invitation: Invitation) -> bool:
    return (
        invitation.accepted_at is None
        and invitation.revoked_at is None
        and invitation.expires_at > _now()
    )


async def _is_member(session: AsyncSession, org_id: uuid.UUID, email: str) -> bool:
    found = await session.scalar(
        select(OrganisationMember.id)
        .join(User, User.id == OrganisationMember.user_id)
        .where(OrganisationMember.organisation_id == org_id, User.email == email)
    )
    return found is not None


async def create(
    session: AsyncSession, access: OrgAccess, email: str, role: OrgRole, meta: RequestMeta
) -> tuple[Invitation, str, bool]:
    """Create an invitation. Returns it, the link to share, and whether it was emailed."""
    if role == OrgRole.OWNER and not access.is_owner_level:
        raise ForbiddenError("Only owners can grant, change or remove the owner role")
    org = access.organisation
    email = normalise_email(email)
    await enforce(session, org.id, "members")
    if await _is_member(session, org.id, email):
        raise ConflictError("This user is already a member")
    # A fresh invitation replaces any earlier one for the same address.
    await session.execute(
        update(Invitation)
        .where(
            Invitation.organisation_id == org.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        organisation_id=org.id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by_id=access.user.id,
        expires_at=_now() + timedelta(days=get_settings().invitation_ttl_days),
    )
    session.add(invitation)
    await session.flush()
    audit.record(
        session,
        action="invitation.created",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org.id,
        target_type="invitation",
        target_id=invitation.id,
        details={"email": email, "role": role.value},
    )
    await session.commit()
    await session.refresh(invitation)
    link = invite_url(token)
    sent = await send_email(
        email,
        f"You are invited to {org.name}",
        f"{access.user.full_name} invited you to join {org.name} as {role.value.replace('_', ' ')}"
        f" on {get_settings().product_name}.\n\nOpen this link to accept:\n{link}\n\n"
        f"The link expires in {get_settings().invitation_ttl_days} days. If you did not expect "
        "this invitation, you can ignore this email.\n",
    )
    return invitation, link, sent


async def list_pending(session: AsyncSession, org_id: uuid.UUID) -> list[Invitation]:
    rows = await session.scalars(
        select(Invitation)
        .where(
            Invitation.organisation_id == org_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > _now(),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


async def revoke(
    session: AsyncSession, access: OrgAccess, invitation_id: uuid.UUID, meta: RequestMeta
) -> None:
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.organisation_id == access.organisation.id
        )
    )
    if invitation is None or not _is_pending(invitation):
        raise NotFoundError("Invitation not found")
    invitation.revoked_at = _now()
    audit.record(
        session,
        action="invitation.revoked",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=access.organisation.id,
        target_type="invitation",
        target_id=invitation.id,
        details={"email": invitation.email},
    )
    await session.commit()


async def _pending_by_token(
    session: AsyncSession, token: str, *, lock: bool = False
) -> tuple[Invitation, Organisation]:
    query = select(Invitation).where(Invitation.token_hash == hash_token(token))
    if lock:
        query = query.with_for_update()
    invitation = await session.scalar(query)
    if invitation is None or not _is_pending(invitation):
        raise NotFoundError(_INVALID)
    org = await session.get(Organisation, invitation.organisation_id)
    if org is None or not org.is_active:
        raise NotFoundError(_INVALID)
    return invitation, org


async def lookup(session: AsyncSession, token: str) -> tuple[Invitation, Organisation, bool]:
    invitation, org = await _pending_by_token(session, token)
    return invitation, org, await get_by_email(session, invitation.email) is not None


async def _join(
    session: AsyncSession,
    invitation: Invitation,
    user: User,
    meta: RequestMeta,
    *,
    created_account: bool,
) -> None:
    org_id = invitation.organisation_id
    await enforce(session, org_id, "members")
    existing = await session.scalar(
        select(OrganisationMember.id).where(
            OrganisationMember.organisation_id == org_id, OrganisationMember.user_id == user.id
        )
    )
    if existing is not None:
        raise ConflictError("You are already a member of this organisation")
    session.add(OrganisationMember(organisation_id=org_id, user_id=user.id, role=invitation.role))
    invitation.accepted_at = _now()
    invitation.accepted_by_id = user.id
    audit.record(
        session,
        action="invitation.accepted",
        actor_id=user.id,
        meta=meta,
        organisation_id=org_id,
        target_type="invitation",
        target_id=invitation.id,
        details={"role": invitation.role.value, "created_account": created_account},
    )
    await session.commit()


async def accept_new(
    session: AsyncSession, token: str, full_name: str, password: str, meta: RequestMeta
) -> Invitation:
    """Accept by creating the account the invitation is addressed to."""
    invitation, _ = await _pending_by_token(session, token, lock=True)
    if await get_by_email(session, invitation.email) is not None:
        raise ConflictError(
            "An account already exists for this email. Sign in to accept the invitation.",
            code="account_exists",
        )
    user = build_user(invitation.email, full_name, password)
    session.add(user)
    await session.flush()
    await _join(session, invitation, user, meta, created_account=True)
    return invitation


async def accept_existing(
    session: AsyncSession, user: User, token: str, meta: RequestMeta
) -> Invitation:
    """Accept as the signed-in user, who must be the account the invitation names."""
    invitation, _ = await _pending_by_token(session, token, lock=True)
    if normalise_email(user.email) != invitation.email:
        raise ForbiddenError(
            "This invitation is for a different email address. Sign in with that address."
        )
    await _join(session, invitation, user, meta, created_account=False)
    return invitation
