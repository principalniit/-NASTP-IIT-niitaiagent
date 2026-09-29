import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_var
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.audit_logs.models import AuditLog


def record(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
    organisation_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the current transaction. The caller commits."""
    session.add(
        AuditLog(
            action=action,
            actor_user_id=actor_id,
            organisation_id=organisation_id,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
            ip_address=meta.ip if meta else None,
            request_id=request_id_var.get(),
        )
    )


async def list_for_organisation(
    session: AsyncSession, organisation_id: uuid.UUID, params: PageParams, action: str | None
) -> tuple[list[AuditLog], int]:
    query = select(AuditLog).where(AuditLog.organisation_id == organisation_id)
    if action:
        query = query.where(AuditLog.action.startswith(action, autoescape=True))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(AuditLog.created_at.desc()).offset(params.offset).limit(params.page_size)
    )
    return list(rows), total
