"""Data retention (off by default), white-label reports and the platform audit log."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.core.database import get_session_factory
from app.modules.audit_logs.models import AuditLog
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlPage, CrawlStatus, FetchStatus
from app.modules.monitoring.retention import apply_retention
from app.modules.organisations.models import Organisation
from app.modules.reports.models import Report, ReportStatus
from tests.conftest import add_member, make_org, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed
from tests.integration.test_reports_api import generate, html_of


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def _crawls(org_id: uuid.UUID, project_id: uuid.UUID, count: int) -> list[uuid.UUID]:
    """Finished crawls, oldest first, each with two pages. Only the oldest is analysed."""
    ids = []
    async with get_session_factory()() as session:
        for n in range(count):
            job = CrawlJob(
                organisation_id=org_id,
                project_id=project_id,
                status=CrawlStatus.COMPLETED,
                config={},
                analysis_status=AnalysisStatus.COMPLETED if n == 0 else AnalysisStatus.NONE,
                created_at=datetime.now(UTC) - timedelta(days=count - n),
            )
            session.add(job)
            await session.flush()
            for path in ("/", "/about"):
                session.add(
                    CrawlPage(
                        organisation_id=org_id,
                        crawl_job_id=job.id,
                        url=f"http://x{path}",
                        discovered_via="link",
                        fetch_status=FetchStatus.FETCHED,
                        redirect_chain=[],
                        structured_data={},
                    )
                )
            ids.append(job.id)
        await session.commit()
    return ids


async def _set_policy(org_id: uuid.UUID, **policy: int) -> None:
    async with get_session_factory()() as session:
        org = await session.get(Organisation, org_id)
        assert org is not None
        org.settings = {**org.settings, "data_retention": policy}
        await session.commit()


async def _pages(crawl_id: uuid.UUID) -> int:
    async with get_session_factory()() as session:
        return (
            await session.scalar(select(func.count()).where(CrawlPage.crawl_job_id == crawl_id))
            or 0
        )


async def test_retention_is_off_by_default(project) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    crawls = await _crawls(org_id, project_id, 4)
    assert await apply_retention() == {"crawls_pruned": 0, "reports_deleted": 0}
    assert [await _pages(c) for c in crawls] == [2, 2, 2, 2]


async def test_old_page_data_is_pruned_but_history_stays(project) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    oldest_analysed, second, third, newest = await _crawls(org_id, project_id, 4)
    await _set_policy(org_id, keep_crawls=2)

    assert (await apply_retention())["crawls_pruned"] == 1
    # The two newest keep their pages; the oldest is the latest analysed crawl, so it is kept.
    assert await _pages(newest) == 2 and await _pages(third) == 2
    assert await _pages(oldest_analysed) == 2
    assert await _pages(second) == 0
    async with get_session_factory()() as session:
        pruned = await session.get(CrawlJob, second)
        assert pruned is not None and pruned.pages_pruned_at is not None  # the crawl record stays
        entry = await session.scalar(select(AuditLog).where(AuditLog.action == "retention.applied"))
        assert entry is not None and entry.details == {"crawls_pruned": 1, "reports_deleted": 0}
    assert (await apply_retention())["crawls_pruned"] == 0  # already pruned, nothing repeated


async def test_old_reports_are_deleted(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await analysed(client, site)
    old = await generate(client, owner, project["id"])
    recent = await generate(client, owner, project["id"])
    async with get_session_factory()() as session:
        await session.execute(
            update(Report)
            .where(Report.id == uuid.UUID(old["id"]))
            .values(created_at=datetime.now(UTC) - timedelta(days=45))
        )
        queued = Report(
            organisation_id=uuid.UUID(org["id"]),
            project_id=uuid.UUID(project["id"]),
            title="Queued",
            status=ReportStatus.QUEUED,
            created_at=datetime.now(UTC) - timedelta(days=90),
        )
        session.add(queued)
        await session.commit()
    await _set_policy(uuid.UUID(org["id"]), delete_reports_after_days=30)
    assert (await apply_retention())["reports_deleted"] == 1
    assert (
        await client.get(f"/api/v1/reports/{old['id']}", headers=owner.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/reports/{recent['id']}", headers=owner.headers)
    ).status_code == 200


async def test_retention_settings_are_validated(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    url = f"/api/v1/organisations/{org['id']}"
    for bad in ({"keep_crawls": 1}, {"delete_reports_after_days": 7}):
        response = await client.patch(
            url, json={"settings": {"data_retention": bad}}, headers=admin.headers
        )
        assert response.status_code == 422, bad
    ok = await client.patch(
        url, json={"settings": {"data_retention": {"keep_crawls": 5}}}, headers=admin.headers
    )
    assert ok.status_code == 200 and ok.json()["settings"]["data_retention"]["keep_crawls"] == 5


async def test_white_label_report(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await analysed(client, site)
    await client.patch(
        f"/api/v1/organisations/{org['id']}",
        json={
            "settings": {
                "report_branding": {
                    "display_name": "Client University",
                    "cover_note": "Prepared by the digital team for the Board",
                }
            }
        },
        headers=owner.headers,
    )
    html = await html_of(client, owner, (await generate(client, owner, project["id"]))["id"])
    assert "Client University" in html and "Prepared by the digital team for the Board" in html
    assert f">{org['name']}<" not in html  # the organisation's own name is replaced


async def test_platform_audit_log(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    owner = await make_user(client, "owner@example.org")
    await add_member(client, admin, org["id"], owner, "owner")
    assert (await client.get("/api/v1/admin/audit-logs", headers=owner.headers)).status_code == 403

    everything = (await client.get("/api/v1/admin/audit-logs", headers=admin.headers)).json()
    actions = {e["action"] for e in everything["items"]}
    assert "auth.login" in actions  # sign-ins belong to no organisation
    assert "organisation.created" in actions
    platform = (
        await client.get(
            "/api/v1/admin/audit-logs", params={"platform_only": "true"}, headers=admin.headers
        )
    ).json()
    assert platform["items"] and all(e["organisation_id"] is None for e in platform["items"])
