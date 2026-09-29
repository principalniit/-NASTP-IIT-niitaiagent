from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ForbiddenError
from app.core.pagination import Page, PageParams, page_params
from app.modules.audit_logs.models import AuditLog
from app.modules.audit_logs.schemas import AuditLogOut
from app.modules.auth.dependencies import CurrentUser

router = APIRouter(tags=["administration"])


@router.get("/admin/audit-logs", response_model=Page[AuditLogOut])
async def platform_audit_logs(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    paging: Annotated[PageParams, Depends(page_params)],
    action: Annotated[str | None, Query(max_length=100)] = None,
    platform_only: bool = False,
) -> Page[AuditLogOut]:
    """Every audit entry, including sign-ins and plan changes that belong to no single
    organisation. Platform administrators only."""
    if not user.is_platform_admin:
        raise ForbiddenError("Only platform administrators can view the platform audit log")
    query = select(AuditLog)
    if platform_only:
        query = query.where(AuditLog.organisation_id.is_(None))
    if action:
        query = query.where(AuditLog.action.startswith(action, autoescape=True))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(AuditLog.created_at.desc()).offset(paging.offset).limit(paging.page_size)
    )
    return Page(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )
