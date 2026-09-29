"""Crawl schedules: settings per project, and the worker step that starts due crawls.

Two switches must both be on for anything to run: SCHEDULER_ENABLED on the server and
the project's own schedule. Both default to off.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.crawler.models import CrawlJob, CrawlStatus
from app.modules.crawler.service import build_config
from app.modules.monitoring.models import CrawlSchedule, Frequency
from app.modules.monitoring.schemas import ScheduleIn, ScheduleOut
from app.modules.organisations.dependencies import ProjectAccess
from app.modules.organisations.models import Organisation
from app.modules.projects.models import Project

logger = logging.getLogger(__name__)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def _at(day: datetime, hour: int, zone: ZoneInfo) -> datetime:
    return datetime.combine(day.date(), time(hour), tzinfo=zone).astimezone(UTC)


def _add_months(day: datetime, months: int) -> datetime:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    for d in (day.day, 30, 29, 28):
        try:
            return day.replace(year=year, month=month, day=d)
        except ValueError:
            continue
    raise ValueError("unreachable")


def first_run(now: datetime, hour: int, timezone: str) -> datetime:
    """The next time the clock shows `hour`:00 in the organisation's time zone."""
    zone = _zone(timezone)
    local = now.astimezone(zone)
    candidate = _at(local, hour, zone)
    return candidate if candidate > now else _at(local + timedelta(days=1), hour, zone)


def following_run(
    previous: datetime, now: datetime, frequency: Frequency, hour: int, timezone: str
) -> datetime:
    """The run after `previous`. Missed runs are skipped, never replayed in a burst."""
    zone = _zone(timezone)
    local = previous.astimezone(zone)
    while True:
        if frequency == Frequency.DAILY:
            local = local + timedelta(days=1)
        elif frequency == Frequency.WEEKLY:
            local = local + timedelta(days=7)
        else:
            local = _add_months(local, 1)
        candidate = _at(local, hour, zone)
        if candidate > now:
            return candidate


async def _org(session: AsyncSession, project: Project) -> Organisation:
    org = await session.get(Organisation, project.organisation_id)
    assert org is not None  # noqa: S101 - a live project always has its organisation
    return org


def _out(row: CrawlSchedule | None, timezone: str) -> ScheduleOut:
    return ScheduleOut(
        enabled=row.enabled if row else False,
        frequency=row.frequency if row else Frequency.WEEKLY,
        hour=row.hour if row else 2,
        timezone=timezone,
        next_run_at=row.next_run_at if row else None,
        last_run_at=row.last_run_at if row else None,
        platform_enabled=get_settings().scheduler_enabled,
    )


async def _row(session: AsyncSession, project: Project) -> CrawlSchedule | None:
    row: CrawlSchedule | None = await session.scalar(
        select(CrawlSchedule).where(
            CrawlSchedule.project_id == project.id,
            CrawlSchedule.organisation_id == project.organisation_id,
        )
    )
    return row


async def get_schedule(session: AsyncSession, project: Project) -> ScheduleOut:
    return _out(await _row(session, project), (await _org(session, project)).timezone)


async def save_schedule(
    session: AsyncSession, access: ProjectAccess, body: ScheduleIn, meta: RequestMeta
) -> ScheduleOut:
    project = access.project
    timezone = (await _org(session, project)).timezone
    row = await _row(session, project)
    if row is None:
        row = CrawlSchedule(organisation_id=project.organisation_id, project_id=project.id)
        session.add(row)
    row.enabled, row.frequency, row.hour = body.enabled, body.frequency, body.hour
    row.updated_by_id = access.user.id
    row.next_run_at = first_run(datetime.now(UTC), body.hour, timezone) if body.enabled else None
    await session.flush()
    audit.record(
        session,
        action="schedule.updated",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="project",
        target_id=project.id,
        details=body.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(row)
    return _out(row, timezone)


async def process_due_schedules(
    factory: async_sessionmaker[AsyncSession] | None = None, now: datetime | None = None
) -> int:
    """Queue a crawl for every due schedule. Returns how many crawls were queued."""
    if not get_settings().scheduler_enabled:
        return 0
    factory = factory or get_session_factory()
    now = now or datetime.now(UTC)
    queued = 0
    async with factory() as session:
        due = list(
            await session.scalars(
                select(CrawlSchedule)
                .where(CrawlSchedule.enabled.is_(True), CrawlSchedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            )
        )
        for schedule in due:
            project = await session.get(Project, schedule.project_id)
            org = await session.get(Organisation, schedule.organisation_id)
            if (
                project is None
                or org is None
                or project.deleted_at is not None
                or not org.is_active
            ):
                schedule.enabled, schedule.next_run_at = False, None
                continue
            schedule.next_run_at = following_run(
                schedule.next_run_at or now, now, schedule.frequency, schedule.hour, org.timezone
            )
            job = CrawlJob(
                organisation_id=project.organisation_id,
                project_id=project.id,
                requested_by_id=None,
                status=CrawlStatus.QUEUED,
                config=(await build_config(session, project)).model_dump(),
            )
            try:
                async with session.begin_nested():
                    session.add(job)
                    await session.flush()
            except IntegrityError:
                logger.info(
                    "Scheduled crawl skipped: one is already active",
                    extra={"project_id": str(project.id)},
                )
                continue
            schedule.last_run_at = now
            audit.record(
                session,
                action="crawl.scheduled",
                actor_id=None,
                organisation_id=project.organisation_id,
                target_type="crawl",
                target_id=job.id,
                details={"project_id": str(project.id), "frequency": schedule.frequency.value},
            )
            queued += 1
        await session.commit()
    return queued
