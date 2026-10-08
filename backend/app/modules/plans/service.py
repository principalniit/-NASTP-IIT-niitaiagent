"""Plan lookup, usage counting and limit enforcement.

Usage is counted from the records themselves (projects, members, crawls, AI tasks,
reports), so there is no separate counter to drift. Monthly and daily periods are
calendar periods in UTC.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.request_context import RequestMeta
from app.modules.ai.models import AIAnalysis
from app.modules.audit_logs import service as audit
from app.modules.audit_logs.models import AuditLog
from app.modules.crawler.models import CrawlJob
from app.modules.organisations.models import Organisation, OrganisationMember
from app.modules.plans.models import Plan
from app.modules.plans.schemas import (
    PlanCreate,
    PlanLimits,
    PlanOut,
    PlanUpdate,
    Resource,
    UsageItem,
    UsageOut,
)
from app.modules.projects.models import Project
from app.modules.users.models import User

UNLIMITED = Plan(key="internal", name="Internal", description=None, limits={}, is_default=True)

LABELS: dict[Resource, tuple[str, str]] = {
    "projects": ("max_projects", "projects"),
    "members": ("max_members", "members"),
    "crawls_per_month": ("max_crawls_per_month", "crawls a month"),
    "ai_tasks_per_day": ("max_ai_tasks_per_day", "AI tasks a day"),
    "reports_per_month": ("max_reports_per_month", "reports a month"),
}


class PlanLimitError(AppError):
    status_code = 409

    def __init__(self, message: str) -> None:
        super().__init__(message, code="plan_limit_reached")


def periods(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day.replace(day=1), day


async def plan_for(session: AsyncSession, org: Organisation) -> Plan:
    if org.plan_id is not None:
        plan = await session.get(Plan, org.plan_id)
        if plan is not None:
            return plan
    default: Plan | None = await session.scalar(select(Plan).where(Plan.is_default.is_(True)))
    return default or UNLIMITED


def limits_of(plan: Plan) -> PlanLimits:
    return PlanLimits.model_validate(plan.limits or {})


async def _count(session: AsyncSession, org_id: uuid.UUID, resource: Resource) -> int:
    month, day = periods()
    queries: dict[Resource, Any] = {
        "projects": select(func.count()).where(
            Project.organisation_id == org_id, Project.deleted_at.is_(None)
        ),
        "members": select(func.count()).where(OrganisationMember.organisation_id == org_id),
        "crawls_per_month": select(func.count()).where(
            CrawlJob.organisation_id == org_id, CrawlJob.created_at >= month
        ),
        "ai_tasks_per_day": select(func.count()).where(
            AIAnalysis.organisation_id == org_id, AIAnalysis.created_at >= day
        ),
        # Counted from the append-only audit log, so deleting a report does not free quota.
        "reports_per_month": select(func.count()).where(
            AuditLog.organisation_id == org_id,
            AuditLog.action == "report.requested",
            AuditLog.created_at >= month,
        ),
    }
    return await session.scalar(queries[resource]) or 0


async def lock_usage(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Serialise usage checks for one organisation until the transaction ends."""
    key = int.from_bytes(org_id.bytes[:8], "big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def enforce(session: AsyncSession, org_id: uuid.UUID, resource: Resource) -> None:
    """Raise PlanLimitError if one more `resource` would exceed the organisation's plan.

    Takes a per-organisation lock held until the caller's transaction ends, so concurrent
    requests count one after another and cannot together overshoot a limit.
    """
    await lock_usage(session, org_id)
    org = await session.get(Organisation, org_id)
    if org is None:
        return
    plan = await plan_for(session, org)
    field, noun = LABELS[resource]
    limit = getattr(limits_of(plan), field)
    if limit is None:
        return
    if await _count(session, org_id, resource) >= limit:
        raise PlanLimitError(
            f"The {plan.name} plan allows {limit} {noun}, and this organisation has reached it. "
            "A platform administrator can change the plan."
        )


async def pages_cap(session: AsyncSession, org: Organisation) -> int | None:
    return limits_of(await plan_for(session, org)).max_pages_per_crawl


async def usage(session: AsyncSession, org: Organisation) -> UsageOut:
    plan = await plan_for(session, org)
    limits = limits_of(plan)
    month, day = periods()
    return UsageOut(
        plan=PlanOut.model_validate(plan) if plan is not UNLIMITED else _unlimited_out(),
        plan_assigned=org.plan_id is not None,
        usage={
            resource: UsageItem(
                used=await _count(session, org.id, resource), limit=getattr(limits, field)
            )
            for resource, (field, _) in LABELS.items()
        },
        max_pages_per_crawl=limits.max_pages_per_crawl,
        month_starts=month,
        day_starts=day,
    )


def _unlimited_out() -> PlanOut:
    return PlanOut(
        id=uuid.UUID(int=0),
        key=UNLIMITED.key,
        name=UNLIMITED.name,
        description="No plan limits are configured.",
        limits=PlanLimits(),
        is_default=True,
        updated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------- administration


async def list_plans(session: AsyncSession) -> list[Plan]:
    return list(await session.scalars(select(Plan).order_by(Plan.created_at)))


async def create_plan(
    session: AsyncSession, user: User, body: PlanCreate, meta: RequestMeta
) -> Plan:
    if await session.scalar(select(Plan.id).where(Plan.key == body.key)):
        raise ConflictError("A plan with this key already exists")
    plan = Plan(
        key=body.key,
        name=body.name,
        description=body.description,
        limits=body.limits.model_dump(),
    )
    session.add(plan)
    await session.flush()
    audit.record(
        session,
        action="plan.created",
        actor_id=user.id,
        meta=meta,
        target_type="plan",
        target_id=plan.id,
        details={"key": plan.key, "limits": plan.limits},
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def update_plan(
    session: AsyncSession, user: User, plan_id: uuid.UUID, body: PlanUpdate, meta: RequestMeta
) -> Plan:
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    if body.is_default is False:
        raise ValidationAppError("Make another plan the default instead")
    if body.name is not None:
        plan.name = body.name
    if body.description is not None:
        plan.description = body.description
    if body.limits is not None:
        plan.limits = body.limits.model_dump()
    if body.is_default:
        for other in await session.scalars(select(Plan).where(Plan.is_default.is_(True))):
            other.is_default = False
        plan.is_default = True
    audit.record(
        session,
        action="plan.updated",
        actor_id=user.id,
        meta=meta,
        target_type="plan",
        target_id=plan.id,
        details=body.model_dump(exclude_none=True, mode="json"),
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def assign_plan(
    session: AsyncSession, user: User, org: Organisation, plan_key: str, meta: RequestMeta
) -> Organisation:
    plan = await session.scalar(select(Plan).where(Plan.key == plan_key))
    if plan is None:
        raise NotFoundError("Plan not found")
    previous = org.plan_id
    org.plan_id = plan.id
    audit.record(
        session,
        action="organisation.plan_changed",
        actor_id=user.id,
        meta=meta,
        organisation_id=org.id,
        target_type="organisation",
        target_id=org.id,
        details={"plan": plan.key, "previous_plan_id": str(previous) if previous else None},
    )
    await session.commit()
    await session.refresh(org)
    return org
