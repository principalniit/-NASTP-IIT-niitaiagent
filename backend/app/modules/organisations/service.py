import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.organisations.dependencies import OrgAccess
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.organisations.permissions import PLATFORM_ADMIN_PERMISSIONS, permissions_for
from app.modules.organisations.schemas import (
    MemberCreate,
    OrganisationCreate,
    OrganisationOut,
    OrganisationSettings,
    OrganisationUpdate,
)
from app.modules.plans.service import enforce
from app.modules.users.models import User
from app.modules.users.service import build_user, get_by_email


def to_out(org: Organisation, role: OrgRole | None, user: User) -> OrganisationOut:
    out = OrganisationOut.model_validate(org)
    out.my_role = role
    if role is not None:
        out.my_permissions = permissions_for(role)
    elif user.is_platform_admin:
        out.my_permissions = sorted(p.value for p in PLATFORM_ADMIN_PERMISSIONS)
    return out


_REQUIRED_FIELDS = frozenset({"name", "timezone", "language", "settings"})


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    return slug or "organisation"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    candidate, n = base, 1
    while await session.scalar(select(Organisation.id).where(Organisation.slug == candidate)):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def list_for_user(
    session: AsyncSession, user: User, params: PageParams
) -> tuple[list[OrganisationOut], int]:
    role_col = OrganisationMember.role
    query = (
        select(Organisation, role_col)
        .outerjoin(
            OrganisationMember,
            (OrganisationMember.organisation_id == Organisation.id)
            & (OrganisationMember.user_id == user.id),
        )
        .order_by(Organisation.name)
    )
    if not user.is_platform_admin:
        query = query.where(role_col.is_not(None), Organisation.is_active.is_(True))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(query.offset(params.offset).limit(params.page_size))
    return [to_out(org, role, user) for org, role in rows.all()], total


async def create(
    session: AsyncSession, user: User, data: OrganisationCreate, meta: RequestMeta
) -> Organisation:
    if data.slug:
        if await session.scalar(select(Organisation.id).where(Organisation.slug == data.slug)):
            raise ConflictError("Slug is already in use")
        slug = data.slug
    else:
        slug = await _unique_slug(session, _slugify(data.name))
    org = Organisation(
        name=data.name,
        slug=slug,
        domain=data.domain,
        logo_url=data.logo_url,
        timezone=data.timezone,
        language=data.language,
        settings=OrganisationSettings().model_dump(mode="json"),
    )
    session.add(org)
    await session.flush()
    session.add(OrganisationMember(organisation_id=org.id, user_id=user.id, role=OrgRole.OWNER))
    audit.record(
        session,
        action="organisation.created",
        actor_id=user.id,
        meta=meta,
        organisation_id=org.id,
        target_type="organisation",
        target_id=org.id,
        details={"name": org.name, "slug": org.slug},
    )
    await session.commit()
    return org


async def update(
    session: AsyncSession, access: OrgAccess, data: OrganisationUpdate, meta: RequestMeta
) -> Organisation:
    org = access.organisation
    changes = data.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        if value is None and field in _REQUIRED_FIELDS:
            raise AppError(f"{field} cannot be null", code="validation_error")
        setattr(org, field, value)
    audit.record(
        session,
        action="organisation.updated",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org.id,
        target_type="organisation",
        target_id=org.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    await session.refresh(org)
    return org


async def list_members(
    session: AsyncSession, organisation_id: uuid.UUID, params: PageParams
) -> tuple[list[OrganisationMember], int]:
    query = select(OrganisationMember).where(OrganisationMember.organisation_id == organisation_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.join(User, User.id == OrganisationMember.user_id)
        .order_by(User.full_name)
        .offset(params.offset)
        .limit(params.page_size)
    )
    return list(rows.unique()), total


async def _owner_count(session: AsyncSession, organisation_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).where(
                OrganisationMember.organisation_id == organisation_id,
                OrganisationMember.role == OrgRole.OWNER,
            )
        )
        or 0
    )


def _check_owner_privilege(access: OrgAccess, *roles: OrgRole) -> None:
    if OrgRole.OWNER in roles and not access.is_owner_level:
        raise ForbiddenError("Only owners can grant, change or remove the owner role")


async def add_member(
    session: AsyncSession, access: OrgAccess, data: MemberCreate, meta: RequestMeta
) -> OrganisationMember:
    _check_owner_privilege(access, data.role)
    org_id = access.organisation.id
    await enforce(session, org_id, "members")
    user = await get_by_email(session, data.email)
    created_account = False
    if user is None:
        if not data.full_name or not data.password:
            raise AppError(
                "No account exists for this email. Provide full_name and an initial password.",
                code="account_details_required",
            )
        user = build_user(data.email, data.full_name, data.password)
        session.add(user)
        await session.flush()
        created_account = True
    elif await _find_member_by_user(session, org_id, user.id):
        raise ConflictError("This user is already a member")
    member = OrganisationMember(organisation_id=org_id, user_id=user.id, role=data.role)
    session.add(member)
    audit.record(
        session,
        action="member.added",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org_id,
        target_type="user",
        target_id=user.id,
        details={"role": data.role.value, "created_account": created_account},
    )
    await session.commit()
    await session.refresh(member)
    return member


async def _find_member_by_user(
    session: AsyncSession, organisation_id: uuid.UUID, user_id: uuid.UUID
) -> OrganisationMember | None:
    member: OrganisationMember | None = await session.scalar(
        select(OrganisationMember).where(
            OrganisationMember.organisation_id == organisation_id,
            OrganisationMember.user_id == user_id,
        )
    )
    return member


async def _get_member(
    session: AsyncSession, organisation_id: uuid.UUID, member_id: uuid.UUID
) -> OrganisationMember:
    member: OrganisationMember | None = await session.scalar(
        select(OrganisationMember).where(
            OrganisationMember.id == member_id,
            OrganisationMember.organisation_id == organisation_id,
        )
    )
    if member is None:
        raise NotFoundError("Member not found")
    return member


async def update_member_role(
    session: AsyncSession,
    access: OrgAccess,
    member_id: uuid.UUID,
    role: OrgRole,
    meta: RequestMeta,
) -> OrganisationMember:
    org_id = access.organisation.id
    member = await _get_member(session, org_id, member_id)
    _check_owner_privilege(access, member.role, role)
    demoting_owner = member.role == OrgRole.OWNER and role != OrgRole.OWNER
    if demoting_owner and await _owner_count(session, org_id) <= 1:
        raise ConflictError("An organisation must keep at least one owner")
    previous = member.role
    member.role = role
    audit.record(
        session,
        action="member.role_changed",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org_id,
        target_type="user",
        target_id=member.user_id,
        details={"from": previous.value, "to": role.value},
    )
    await session.commit()
    await session.refresh(member)
    return member


async def remove_member(
    session: AsyncSession, access: OrgAccess, member_id: uuid.UUID, meta: RequestMeta
) -> None:
    org_id = access.organisation.id
    member = await _get_member(session, org_id, member_id)
    _check_owner_privilege(access, member.role)
    if member.role == OrgRole.OWNER and await _owner_count(session, org_id) <= 1:
        raise ConflictError("An organisation must keep at least one owner")
    audit.record(
        session,
        action="member.removed",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=org_id,
        target_type="user",
        target_id=member.user_id,
        details={"role": member.role.value},
    )
    await session.delete(member)
    await session.commit()
