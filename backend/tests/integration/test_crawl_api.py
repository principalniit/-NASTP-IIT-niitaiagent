"""Crawl lifecycle through the API and the worker, against the local fixture site."""

import asyncio
import ipaddress
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.database import get_session_factory
from app.modules.crawler.engine import CrawlEngine
from app.modules.crawler.models import CrawlJob, CrawlStatus
from app.modules.crawler.url_safety import SafetyPolicy
from app.modules.projects.models import Project
from app.worker import claim_next_job, process_next_job, recover_stale_jobs
from tests.conftest import TestUser, add_member, make_org, make_project, make_user
from tests.fixtures.site import FixtureSite, build_standard_site


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


def engine_for(site: FixtureSite):  # type: ignore[no-untyped-def]
    policy = SafetyPolicy(
        allowed_ports=frozenset({80, 443, site.port}),
        allowed_private_networks=(ipaddress.ip_network("127.0.0.1/32"),),
    )
    return lambda job_id: CrawlEngine(job_id, policy=policy)


async def point_project_at(site: FixtureSite, project_id: str) -> None:
    """Project creation rejects local addresses, so tests re-point a project in the DB."""
    async with get_session_factory()() as session:
        await session.execute(
            update(Project)
            .where(Project.id == uuid.UUID(project_id))
            .values(root_url=f"{site.base}/", domain="127.0.0.1")
        )
        await session.commit()


async def setup(client: AsyncClient, site: FixtureSite) -> tuple[TestUser, dict, dict]:  # type: ignore[type-arg]
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    org = await make_org(client, owner, "Org")
    project = await make_project(client, owner, org["id"])
    await point_project_at(site, project["id"])
    settings_url = f"/api/v1/projects/{project['id']}/settings"
    settings = (await client.get(settings_url, headers=owner.headers)).json()["settings"]
    settings["crawl"]["delay_ms"] = 0
    settings["excluded_paths"] = ["/wp-admin/*"]
    assert (await client.put(settings_url, json=settings, headers=owner.headers)).status_code == 200
    return owner, org, project


async def test_crawl_lifecycle_and_results(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await setup(client, site)
    started = await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    assert started.status_code == 201, started.text
    crawl = started.json()
    assert crawl["status"] == "queued"
    assert crawl["config"]["max_pages"] == 100 and crawl["config"]["delay_ms"] == 0
    assert crawl["project_name"] == "Site"

    again = await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    assert again.status_code == 409

    assert await process_next_job("test-worker", engine_factory=engine_for(site))
    assert not await process_next_job("test-worker", engine_factory=engine_for(site))

    url = f"/api/v1/crawls/{crawl['id']}"
    done = (await client.get(url, headers=owner.headers)).json()
    assert done["status"] == "completed"
    assert done["robots_status"] == "found"
    assert done["pages_crawled"] > 10 and done["finished_at"]

    summary = (await client.get(f"{url}/summary", headers=owner.headers)).json()
    assert summary["status_classes"]["4xx"] == 1
    assert summary["status_classes"]["5xx"] == 1
    assert summary["orphan_pages"] == 1
    assert summary["broken_internal_links"] == 2
    assert summary["redirects"] == 2
    assert summary["noindex_pages"] == 1
    assert any(
        {u.rsplit("/", 1)[-1] for u in g["urls"]} == {"about", "about-copy"}
        for g in summary["duplicate_content_groups"]
    )

    pages = f"{url}/pages"
    missing = (
        await client.get(pages, params={"status_class": "4xx"}, headers=owner.headers)
    ).json()
    assert [p["url"] for p in missing["items"]] == [f"{site.base}/missing"]
    orphans = (await client.get(pages, params={"orphan": "true"}, headers=owner.headers)).json()
    assert orphans["total"] == 1
    blocked = (
        await client.get(pages, params={"fetch_status": "blocked_by_robots"}, headers=owner.headers)
    ).json()
    assert blocked["total"] == 1
    search = (
        await client.get(
            pages,
            params={"q": "deep", "sort": "depth", "order": "desc", "page_size": 2},
            headers=owner.headers,
        )
    ).json()
    assert search["total"] == 5 and search["items"][0]["depth"] == 5
    bad_sort = await client.get(pages, params={"sort": "error"}, headers=owner.headers)
    assert bad_sort.status_code == 422

    home = (await client.get(pages, params={"q": "Home"}, headers=owner.headers)).json()["items"][0]
    detail = (await client.get(f"{pages}/{home['id']}", headers=owner.headers)).json()
    assert detail["title"] == "Home"
    assert any(
        link["url"].endswith("/missing") and link["status_code"] == 404
        for link in detail["outlinks"]
    )
    assert any(link["url"].endswith("/about") for link in detail["inlinks"])

    broken = (await client.get(f"{url}/broken-links", headers=owner.headers)).json()
    assert {b["target_url"].rsplit("/", 1)[-1] for b in broken["items"]} == {"missing", "error"}

    listing = (
        await client.get(f"/api/v1/organisations/{org['id']}/crawls", headers=owner.headers)
    ).json()
    assert listing["total"] == 1
    filtered = (
        await client.get(
            f"/api/v1/organisations/{org['id']}/crawls",
            params={"status": "running"},
            headers=owner.headers,
        )
    ).json()
    assert filtered["total"] == 0

    incremental = await client.post(
        f"/api/v1/projects/{project['id']}/crawls",
        json={"incremental": True},
        headers=owner.headers,
    )
    assert incremental.json()["incremental"] is True
    assert incremental.json()["previous_crawl_id"] == crawl["id"]


async def test_roles_cancel_and_caps(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await setup(client, site)
    viewer = await make_user(client, "viewer@example.org")
    manager = await make_user(client, "manager@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    await add_member(client, owner, org["id"], manager, "seo_manager")
    start_url = f"/api/v1/projects/{project['id']}/crawls"
    assert (await client.post(start_url, headers=viewer.headers)).status_code == 403

    # Lowering the organisation cap below the project setting clamps the next crawl.
    org_settings = (
        await client.get(f"/api/v1/organisations/{org['id']}", headers=owner.headers)
    ).json()["settings"]
    org_settings["crawl_limits"]["max_pages"] = 3
    await client.patch(
        f"/api/v1/organisations/{org['id']}", json={"settings": org_settings}, headers=owner.headers
    )

    crawl = (
        await client.post(start_url, json={"incremental": True}, headers=manager.headers)
    ).json()
    assert crawl["config"]["max_pages"] == 3
    assert crawl["incremental"] is False  # no previous completed crawl to compare with

    cancel_url = f"/api/v1/crawls/{crawl['id']}/cancel"
    assert (await client.post(cancel_url, headers=viewer.headers)).status_code == 403
    cancelled = await client.post(cancel_url, headers=manager.headers)
    assert cancelled.json()["status"] == "cancelled"
    assert (await client.post(cancel_url, headers=manager.headers)).status_code == 409
    assert not await process_next_job("w", engine_factory=engine_for(site))

    second = (await client.post(start_url, headers=manager.headers)).json()
    await process_next_job("w", engine_factory=engine_for(site))
    done = (await client.get(f"/api/v1/crawls/{second['id']}", headers=viewer.headers)).json()
    assert done["status"] == "completed" and done["pages_discovered"] == 3


async def test_deleting_a_project_cancels_its_queued_crawl(
    client: AsyncClient, site: FixtureSite
) -> None:
    owner, _, project = await setup(client, site)
    crawl = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()
    await client.delete(f"/api/v1/projects/{project['id']}", headers=owner.headers)
    assert (
        await client.get(f"/api/v1/crawls/{crawl['id']}", headers=owner.headers)
    ).status_code == 404
    async with get_session_factory()() as session:
        job = await session.get(CrawlJob, uuid.UUID(crawl["id"]))
        assert job is not None and job.status == CrawlStatus.CANCELLED


async def test_only_one_worker_claims_a_job(client: AsyncClient, site: FixtureSite) -> None:
    owner, _, project = await setup(client, site)
    await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    factory = get_session_factory()
    claims = await asyncio.gather(*(claim_next_job(factory, f"w{i}") for i in range(5)))
    assert sum(1 for c in claims if c is not None) == 1


async def test_stale_and_crashing_jobs_are_failed(client: AsyncClient, site: FixtureSite) -> None:
    owner, _, project = await setup(client, site)
    crawl = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()

    def exploding(job_id: uuid.UUID) -> CrawlEngine:
        engine = CrawlEngine(job_id)

        async def boom() -> CrawlStatus:
            raise RuntimeError("secret internal detail")

        engine.run = boom  # type: ignore[method-assign]
        return engine

    await process_next_job("w", engine_factory=exploding)
    failed = (await client.get(f"/api/v1/crawls/{crawl['id']}", headers=owner.headers)).json()
    assert failed["status"] == "failed"
    assert "secret" not in (failed["error_message"] or "")

    second = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()
    factory = get_session_factory()
    await claim_next_job(factory, "dead-worker")
    async with factory() as session:
        await session.execute(
            update(CrawlJob)
            .where(CrawlJob.id == uuid.UUID(second["id"]))
            .values(heartbeat_at=datetime.now(UTC) - timedelta(minutes=30))
        )
        await session.commit()
    assert await recover_stale_jobs(factory, 300) == 1
    stale = (await client.get(f"/api/v1/crawls/{second['id']}", headers=owner.headers)).json()
    assert stale["status"] == "failed"
    assert "stopped unexpectedly" in stale["error_message"]
