"""Crawl data must never cross organisation boundaries."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.modules.crawler.models import CrawlJob, CrawlPage, CrawlStatus, FetchStatus
from tests.conftest import add_member, make_org, make_project, make_user


async def _crawl_with_page(org_id: str, project_id: str) -> tuple[str, str]:
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=uuid.UUID(org_id),
            project_id=uuid.UUID(project_id),
            status=CrawlStatus.COMPLETED,
            config={},
        )
        session.add(job)
        await session.flush()
        page = CrawlPage(
            organisation_id=job.organisation_id,
            crawl_job_id=job.id,
            url="https://secret.example.org/",
            discovered_via="root",
            fetch_status=FetchStatus.FETCHED,
            status_code=200,
            title="Confidential",
        )
        session.add(page)
        await session.commit()
        return str(job.id), str(page.id)


async def test_crawls_are_isolated_between_organisations(client: AsyncClient) -> None:
    platform = await make_user(client, "platform@example.org", platform_admin=True)
    alice = await make_user(client, "alice@example.org")
    bob = await make_user(client, "bob@example.org")
    org_a = await make_org(client, platform, "A")
    org_b = await make_org(client, platform, "B")
    await add_member(client, platform, org_a["id"], alice, "owner")
    await add_member(client, platform, org_b["id"], bob, "owner")
    project_a = await make_project(client, alice, org_a["id"], "https://a.example.org")
    project_b = await make_project(client, bob, org_b["id"], "https://b.example.org")
    crawl_b, page_b = await _crawl_with_page(org_b["id"], project_b["id"])
    crawl_a, _ = await _crawl_with_page(org_a["id"], project_a["id"])
    h = alice.headers

    for path in (
        f"/api/v1/crawls/{crawl_b}",
        f"/api/v1/crawls/{crawl_b}/summary",
        f"/api/v1/crawls/{crawl_b}/pages",
        f"/api/v1/crawls/{crawl_b}/pages/{page_b}",
        f"/api/v1/crawls/{crawl_b}/broken-links",
        f"/api/v1/organisations/{org_b['id']}/crawls",
    ):
        response = await client.get(path, headers=h)
        assert response.status_code == 404, path
        assert "Confidential" not in response.text

    assert (await client.post(f"/api/v1/crawls/{crawl_b}/cancel", headers=h)).status_code == 404
    assert (
        await client.post(f"/api/v1/projects/{project_b['id']}/crawls", headers=h)
    ).status_code == 404
    # Bob's page ID under Alice's own crawl must not resolve.
    mixed = await client.get(f"/api/v1/crawls/{crawl_a}/pages/{page_b}", headers=h)
    assert mixed.status_code == 404
    # Filtering Alice's organisation listing by Bob's project returns nothing.
    listing = await client.get(
        f"/api/v1/organisations/{org_a['id']}/crawls",
        params={"project_id": project_b["id"]},
        headers=h,
    )
    assert listing.json()["total"] == 0

    async with get_session_factory()() as session:
        job = await session.scalar(select(CrawlJob).where(CrawlJob.id == uuid.UUID(crawl_b)))
        assert job is not None and job.status == CrawlStatus.COMPLETED


async def test_platform_admin_cannot_read_crawls_without_membership(client: AsyncClient) -> None:
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    ops = await make_user(client, "ops@example.org", platform_admin=True)
    org = await make_org(client, owner, "A")
    project = await make_project(client, owner, org["id"])
    crawl, _ = await _crawl_with_page(org["id"], project["id"])
    assert (await client.get(f"/api/v1/crawls/{crawl}", headers=ops.headers)).status_code == 404
    assert (
        await client.get(f"/api/v1/organisations/{org['id']}/crawls", headers=ops.headers)
    ).status_code == 404
