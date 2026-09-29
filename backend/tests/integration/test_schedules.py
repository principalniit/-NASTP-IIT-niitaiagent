"""Crawl schedules: timing rules, the two off-by-default switches, and the worker step."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.crawler.models import CrawlJob, CrawlStatus
from app.modules.monitoring.models import CrawlSchedule, Frequency
from app.modules.monitoring.service import first_run, following_run, process_due_schedules
from app.modules.projects.models import Project
from tests.conftest import add_member, make_org, make_project, make_user

KARACHI = "Asia/Karachi"  # UTC+5, no daylight saving


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_first_run_uses_the_organisation_time_zone() -> None:
    # 05:00 in Karachi: 02:00 has passed today, so the next run is 02:00 tomorrow (21:00 UTC).
    assert first_run(utc(2026, 1, 1, 0, 0), 2, KARACHI) == utc(2026, 1, 1, 21, 0)
    # 04:00 in Karachi: 06:00 is still ahead today.
    assert first_run(utc(2025, 12, 31, 23, 0), 6, KARACHI) == utc(2026, 1, 1, 1, 0)
    assert first_run(utc(2026, 1, 1, 0, 0), 2, "Not/AZone") == utc(2026, 1, 1, 2, 0)


def test_following_runs_and_missed_runs() -> None:
    last = utc(2026, 1, 1, 21, 0)  # 02:00 on 2 January in Karachi
    now = last + timedelta(minutes=1)
    assert following_run(last, now, Frequency.DAILY, 2, KARACHI) == utc(2026, 1, 2, 21, 0)
    assert following_run(last, now, Frequency.WEEKLY, 2, KARACHI) == utc(2026, 1, 8, 21, 0)
    assert following_run(last, now, Frequency.MONTHLY, 2, KARACHI) == utc(2026, 2, 1, 21, 0)
    end_of_month = utc(2026, 1, 30, 21, 0)  # 31 January locally
    assert following_run(end_of_month, end_of_month, Frequency.MONTHLY, 2, KARACHI) == utc(
        2026, 2, 27, 21, 0
    )  # 28 February locally
    # A server that was off for ten days runs once, at the next slot, not ten times.
    later = last + timedelta(days=9, hours=23)  # just before the slot on 12 January
    assert following_run(last, later, Frequency.DAILY, 2, KARACHI) == utc(2026, 1, 11, 21, 0)


async def test_schedule_api(client: AsyncClient) -> None:
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    org = await make_org(client, owner, "Org")
    project = await make_project(client, owner, org["id"])
    viewer = await make_user(client, "viewer@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    url = f"/api/v1/projects/{project['id']}/schedule"

    default = (await client.get(url, headers=viewer.headers)).json()
    assert default["enabled"] is False and default["platform_enabled"] is False
    assert default["next_run_at"] is None and default["frequency"] == "weekly"

    body = {"enabled": True, "frequency": "daily", "hour": 3}
    assert (await client.put(url, json=body, headers=viewer.headers)).status_code == 403
    for bad in ({"enabled": True, "hour": 24}, {"enabled": True, "frequency": "hourly"}, {}):
        assert (await client.put(url, json=bad, headers=owner.headers)).status_code == 422, bad
    saved = (await client.put(url, json=body, headers=owner.headers)).json()
    assert saved["enabled"] is True and saved["hour"] == 3 and saved["next_run_at"]
    off = (await client.put(url, json={"enabled": False}, headers=owner.headers)).json()
    assert off["enabled"] is False and off["next_run_at"] is None
    audit = (
        await client.get(f"/api/v1/organisations/{org['id']}/audit-logs", headers=owner.headers)
    ).json()
    assert "schedule.updated" in {e["action"] for e in audit["items"]}


async def test_due_schedules_queue_crawls_only_when_switched_on(
    project, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    past = datetime.now(UTC) - timedelta(minutes=5)
    async with get_session_factory()() as session:
        session.add(
            CrawlSchedule(
                organisation_id=org_id,
                project_id=project_id,
                enabled=True,
                frequency=Frequency.WEEKLY,
                hour=2,
                next_run_at=past,
            )
        )
        await session.commit()

    assert await process_due_schedules() == 0  # SCHEDULER_ENABLED is off by default
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    assert await process_due_schedules() == 1
    async with get_session_factory()() as session:
        jobs = list(
            await session.scalars(select(CrawlJob).where(CrawlJob.project_id == project_id))
        )
        assert len(jobs) == 1 and jobs[0].status == CrawlStatus.QUEUED
        assert jobs[0].requested_by_id is None and jobs[0].config["root_url"] == "http://x/"
        schedule = await session.scalar(select(CrawlSchedule))
        assert schedule is not None and schedule.last_run_at is not None
        assert schedule.next_run_at is not None and schedule.next_run_at > datetime.now(UTC)
        # Due again while that crawl is still queued: skipped, not duplicated.
        schedule.next_run_at = past
        await session.commit()
    assert await process_due_schedules() == 0
    async with get_session_factory()() as session:
        count = len(
            list(await session.scalars(select(CrawlJob).where(CrawlJob.project_id == project_id)))
        )
        assert count == 1
        # A deleted project's schedule switches itself off.
        await session.execute(
            update(Project).where(Project.id == project_id).values(deleted_at=datetime.now(UTC))
        )
        await session.execute(update(CrawlSchedule).values(next_run_at=past))
        await session.commit()
    assert await process_due_schedules() == 0
    async with get_session_factory()() as session:
        schedule = await session.scalar(select(CrawlSchedule))
        assert schedule is not None and schedule.enabled is False and schedule.next_run_at is None


async def test_disabled_schedules_never_run(project, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    async with get_session_factory()() as session:
        session.add(
            CrawlSchedule(
                organisation_id=org_id,
                project_id=project_id,
                enabled=False,
                next_run_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await session.commit()
    assert await process_due_schedules() == 0
    assert uuid.UUID(str(project_id))
