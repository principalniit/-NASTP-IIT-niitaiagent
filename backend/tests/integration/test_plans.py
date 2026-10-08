"""Plans and usage limits: administration, assignment, enforcement at every usage point."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.ai.models import AIAnalysis
from app.modules.audit_logs.models import AuditLog
from app.modules.crawler.models import CrawlJob, CrawlStatus
from app.modules.crawler.service import build_config
from app.modules.monitoring.models import CrawlSchedule
from app.modules.monitoring.service import process_due_schedules
from app.modules.projects.models import Project
from app.modules.reports.models import Report
from app.worker import process_next_report
from tests.conftest import TestUser, add_member, make_org, make_project, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed, enable_ai

TIGHT = {
    "max_projects": 1,
    "max_members": 2,
    "max_pages_per_crawl": 40,
    "max_crawls_per_month": 2,
    "max_ai_tasks_per_day": 1,
    "max_reports_per_month": 1,
}


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def make_plan(client: AsyncClient, admin: TestUser, key: str, limits: dict) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        "/api/v1/plans",
        json={"key": key, "name": key.title(), "limits": limits},
        headers=admin.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def assign(client: AsyncClient, admin: TestUser, org_id: str, key: str) -> dict:  # type: ignore[type-arg]
    response = await client.put(
        f"/api/v1/organisations/{org_id}/plan", json={"plan_key": key}, headers=admin.headers
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_plan_administration(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    owner = await make_user(client, "owner@example.org")
    await add_member(client, admin, org["id"], owner, "owner")

    usage = (
        await client.get(f"/api/v1/organisations/{org['id']}/usage", headers=owner.headers)
    ).json()
    assert usage["plan"]["key"] == "internal" and usage["plan_assigned"] is False
    assert all(item["limit"] is None for item in usage["usage"].values())

    starter = await make_plan(client, admin, "tight", TIGHT)
    duplicate = await client.post(
        "/api/v1/plans", json={"key": "tight", "name": "Again"}, headers=admin.headers
    )
    assert duplicate.status_code == 409
    bad = await client.post(
        "/api/v1/plans",
        json={"key": "Bad Key", "name": "X", "limits": {"max_projects": 0}},
        headers=admin.headers,
    )
    assert bad.status_code == 422
    denied = await client.put(
        f"/api/v1/organisations/{org['id']}/plan",
        json={"plan_key": "tight"},
        headers=owner.headers,
    )
    assert denied.status_code == 403  # a member learns why
    missing = await client.put(
        f"/api/v1/organisations/{org['id']}/plan", json={"plan_key": "nope"}, headers=admin.headers
    )
    assert missing.status_code == 404

    usage = await assign(client, admin, org["id"], "tight")
    assert usage["plan"]["key"] == "tight" and usage["plan_assigned"] is True
    assert usage["usage"]["members"] == {"used": 2, "limit": 2}
    assert usage["max_pages_per_crawl"] == 40

    pro = await make_plan(client, admin, "generous", {"max_projects": 5})
    made_default = await client.patch(
        f"/api/v1/plans/{pro['id']}", json={"is_default": True}, headers=admin.headers
    )
    assert made_default.json()["is_default"] is True
    plans = {p["key"]: p for p in (await client.get("/api/v1/plans", headers=admin.headers)).json()}
    assert plans["generous"]["is_default"] and not plans["tight"]["is_default"]
    refused = await client.patch(
        f"/api/v1/plans/{starter['id']}", json={"is_default": False}, headers=admin.headers
    )
    assert refused.status_code == 422
    renamed = await client.patch(
        f"/api/v1/plans/{starter['id']}",
        json={"limits": {**TIGHT, "max_projects": 3}},
        headers=admin.headers,
    )
    assert renamed.json()["limits"]["max_projects"] == 3

    audit = (
        await client.get(f"/api/v1/organisations/{org['id']}/audit-logs", headers=owner.headers)
    ).json()
    assert "organisation.plan_changed" in {e["action"] for e in audit["items"]}


async def test_projects_and_members_are_limited(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    await make_plan(client, admin, "tight", TIGHT)
    await assign(client, admin, org["id"], "tight")

    await make_project(client, admin, org["id"], "https://one.example.org")
    second = await client.post(
        f"/api/v1/organisations/{org['id']}/projects",
        json={"name": "Two", "root_url": "https://two.example.org"},
        headers=admin.headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "plan_limit_reached"
    assert "The Tight plan allows 1 projects" in second.json()["error"]["message"]

    first = await make_user(client, "first@example.org")
    await add_member(client, admin, org["id"], first, "viewer")  # 2 of 2 with the owner
    third = await client.post(
        f"/api/v1/organisations/{org['id']}/members",
        json={
            "email": "third@example.org",
            "role": "viewer",
            "full_name": "Third",
            "password": "correct-horse-battery",
        },
        headers=admin.headers,
    )
    assert third.status_code == 409 and third.json()["error"]["code"] == "plan_limit_reached"


async def test_crawls_ai_and_reports_are_limited(
    client: AsyncClient, site: FixtureSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org, project = await analysed(client, site)  # one crawl used
    await make_plan(client, owner, "tight", TIGHT)
    await assign(client, owner, org["id"], "tight")
    pid = project["id"]

    async with get_session_factory()() as session:
        proj = await session.get(Project, uuid.UUID(pid))
        assert proj is not None
        assert (await build_config(session, proj)).max_pages == 40  # the plan caps pages
        # A second crawl this month, finished, so no crawl is active.
        session.add(
            CrawlJob(
                organisation_id=proj.organisation_id,
                project_id=proj.id,
                status=CrawlStatus.COMPLETED,
                config={},
            )
        )
        await session.commit()
    crawl = await client.post(f"/api/v1/projects/{pid}/crawls", headers=owner.headers)
    assert crawl.status_code == 409 and crawl.json()["error"]["code"] == "plan_limit_reached"

    report = await client.post(f"/api/v1/projects/{pid}/reports", json={}, headers=owner.headers)
    assert report.status_code == 202
    again = await client.post(f"/api/v1/projects/{pid}/reports", json={}, headers=owner.headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "plan_limit_reached"
    # Deleting a report does not give the quota back.
    assert await process_next_report()
    deleted = await client.delete(f"/api/v1/reports/{report.json()['id']}", headers=owner.headers)
    assert deleted.status_code == 204
    after = await client.post(f"/api/v1/projects/{pid}/reports", json={}, headers=owner.headers)
    assert after.status_code == 409

    monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
    monkeypatch.setattr(get_settings(), "ollama_default_model", "llama3.1")
    await enable_ai(client, owner, org["id"])
    url = f"/api/v1/projects/{pid}/ai/analyses"
    assert (
        await client.post(url, json={"kind": "management_summary"}, headers=owner.headers)
    ).status_code == 202
    limited = await client.post(url, json={"kind": "management_summary"}, headers=owner.headers)
    assert limited.status_code == 409 and limited.json()["error"]["code"] == "plan_limit_reached"

    usage = (
        await client.get(f"/api/v1/organisations/{org['id']}/usage", headers=owner.headers)
    ).json()["usage"]
    assert usage["crawls_per_month"] == {"used": 2, "limit": 2}
    assert usage["reports_per_month"] == {"used": 1, "limit": 1}
    assert usage["ai_tasks_per_day"] == {"used": 1, "limit": 1}

    # Records from earlier periods do not count.
    async with get_session_factory()() as session:
        old = datetime.now(UTC) - timedelta(days=40)
        for model in (CrawlJob, Report, AIAnalysis):
            for row in await session.scalars(
                select(model).where(model.project_id == uuid.UUID(pid))
            ):
                row.created_at = old
        for entry in await session.scalars(select(AuditLog)):
            entry.created_at = old
        await session.commit()
    usage = (
        await client.get(f"/api/v1/organisations/{org['id']}/usage", headers=owner.headers)
    ).json()["usage"]
    assert usage["crawls_per_month"]["used"] == 0 and usage["reports_per_month"]["used"] == 0
    assert usage["ai_tasks_per_day"]["used"] == 0


async def test_scheduled_crawls_respect_the_plan(
    client: AsyncClient, project, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    await make_plan(client, admin, "tight", {**TIGHT, "max_crawls_per_month": 1})
    await assign(client, admin, str(org_id), "tight")
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    async with get_session_factory()() as session:
        session.add(
            CrawlJob(
                organisation_id=org_id,
                project_id=project_id,
                status=CrawlStatus.COMPLETED,
                config={},
            )
        )
        session.add(
            CrawlSchedule(
                organisation_id=org_id,
                project_id=project_id,
                enabled=True,
                next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await session.commit()
    assert await process_due_schedules() == 0
    async with get_session_factory()() as session:
        schedule = await session.scalar(select(CrawlSchedule))
        assert schedule is not None and schedule.next_run_at > datetime.now(UTC)  # type: ignore[operator]
