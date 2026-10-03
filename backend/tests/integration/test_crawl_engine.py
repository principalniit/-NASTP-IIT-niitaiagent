"""Crawl engine against a local fixture site."""

import ipaddress
import uuid
from collections.abc import Iterator
from itertools import pairwise
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import get_session_factory
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.engine import CrawlEngine
from app.modules.crawler.models import CrawlJob, CrawlLink, CrawlPage, CrawlStatus, FetchStatus
from app.modules.crawler.url_safety import SafetyPolicy
from tests.fixtures.site import FixtureSite, Response, build_standard_site

UA = "NIIT-SEO-Agent/0.1 (+https://example.org)"


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


def policy_for(site: FixtureSite) -> SafetyPolicy:
    return SafetyPolicy(
        allowed_ports=frozenset({80, 443, site.port}),
        allowed_private_networks=(ipaddress.ip_network("127.0.0.1/32"),),
    )


async def run_crawl(
    site: FixtureSite,
    project: tuple[uuid.UUID, uuid.UUID],
    *,
    previous: uuid.UUID | None = None,
    **overrides: Any,
) -> tuple[CrawlJob, dict[str, CrawlPage]]:
    org_id, project_id = project
    config = CrawlConfig(
        root_url=f"{site.base}/",
        allowed_hosts=["127.0.0.1"],
        excluded_paths=["/wp-admin/*"],
        max_pages=100,
        max_depth=5,
        concurrency=2,
        timeout_seconds=2,
        delay_ms=0,
        user_agent=UA,
        extra_ports=[site.port],
    ).model_copy(update=overrides)
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=org_id,
            project_id=project_id,
            status=CrawlStatus.RUNNING,
            config=config.model_dump(),
            incremental=previous is not None,
            previous_crawl_id=previous,
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    await CrawlEngine(job_id, policy=policy_for(site)).run()
    async with get_session_factory()() as session:
        job = await session.get(CrawlJob, job_id)
        assert job is not None
        rows = await session.scalars(select(CrawlPage).where(CrawlPage.crawl_job_id == job_id))
        pages = {p.url.replace(site.base, ""): p for p in rows}
    return job, pages


async def test_full_crawl_records_observations(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    job, pages = await run_crawl(site, project)
    assert job.status == CrawlStatus.COMPLETED
    assert job.robots_status == "found"
    assert job.sitemap_url_count == 4
    assert job.sitemaps[0]["status"] == "ok"

    home = pages["/"]
    assert home.status_code == 200 and home.fetch_status == FetchStatus.FETCHED
    assert home.title == "Home" and home.depth == 0 and home.discovered_via == "root"
    assert home.canonical_url == f"{site.base}/"
    assert home.images_missing_alt == 1
    assert home.external_links_count == 1
    assert home.response_time_ms is not None and home.etag

    # Redirect recorded with its chain, and the destination recorded as its own page.
    assert pages["/old-page"].status_code == 301
    assert pages["/old-page"].final_url == f"{site.base}/new-page"
    assert pages["/old-page"].redirect_chain[0]["status_code"] == 301
    assert pages["/new-page"].status_code == 200 and pages["/new-page"].title == "New page"

    # Redirects to another host are not followed, even to a loopback address.
    assert pages["/redirect-out"].fetch_status == FetchStatus.REDIRECT_OUT_OF_SCOPE

    assert pages["/missing"].status_code == 404
    assert pages["/error"].status_code == 500
    assert pages["/file.pdf"].fetch_status == FetchStatus.SKIPPED_CONTENT_TYPE
    assert pages["/private/secret"].fetch_status == FetchStatus.BLOCKED_BY_ROBOTS
    assert "/private/secret" not in site.paths()
    assert "/wp-admin/x" not in pages and "/wp-admin/x" not in site.paths()
    assert "/about#team" not in pages  # fragments are not separate pages

    assert pages["/admissions"].is_noindex
    assert pages["/about"].content_hash == pages["/about-copy"].content_hash

    # Orphan: listed in the sitemap, crawled, but no page links to it.
    assert pages["/orphan"].discovered_via == "sitemap"
    assert pages["/orphan"].is_orphan and pages["/orphan"].in_sitemap
    assert not pages["/about"].is_orphan and pages["/about"].inlinks_count >= 2

    # Depth limit: /deep/1 is depth 1, so depth 5 is /deep/5 and /deep/6 is never fetched.
    assert pages["/deep/5"].depth == 5
    assert "/deep/6" not in pages and "/deep/6" not in site.paths()

    assert job.pages_blocked == 1
    assert job.pages_crawled == len(pages) - 1
    assert all(r.user_agent == UA for r in site.requests)


async def test_links_are_stored_and_resolved(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    job, pages = await run_crawl(site, project)
    async with get_session_factory()() as session:
        links = list(
            await session.scalars(
                select(CrawlLink).where(CrawlLink.source_page_id == pages["/"].id)
            )
        )
    by_target = {link.target_url.replace(site.base, ""): link for link in links}
    assert by_target["/missing"].target_page_id == pages["/missing"].id
    assert by_target["https://external.example.com/"].is_internal is False
    assert by_target["/about"].anchor_text == "About us"
    assert all(link.organisation_id == job.organisation_id for link in links)


async def test_page_limit_stops_crawl_and_skips_orphan_detection(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    job, pages = await run_crawl(site, project, max_pages=5)
    assert len(pages) == 5
    assert job.status == CrawlStatus.COMPLETED
    assert any("page limit" in w for w in job.warnings)
    assert not any(p.is_orphan for p in pages.values())


async def test_unreachable_robots_blocks_everything(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    site.routes["/robots.txt"] = Response(503, b"down", {"Content-Type": "text/plain"})
    job, pages = await run_crawl(site, project)
    assert job.robots_status == "unreachable"
    assert pages["/"].fetch_status == FetchStatus.BLOCKED_BY_ROBOTS
    assert "/" not in site.paths()
    assert any("RFC 9309" in w for w in job.warnings)


async def test_missing_robots_and_sitemap_allow_crawl(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    del site.routes["/robots.txt"]
    del site.routes["/sitemap.xml"]
    job, pages = await run_crawl(site, project)
    assert job.robots_status == "not_found"
    assert job.sitemaps[0]["status"] == "not_found"
    assert pages["/private/secret"].status_code == 200
    assert "/orphan" not in pages  # without a sitemap it cannot be discovered


async def test_timeouts_and_size_limits(site: FixtureSite, project, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "crawler_max_response_bytes", 20_000)
    site.page("/", "Home", "<a href='/slow'>Slow</a><a href='/big'>Big</a>")
    site.routes["/slow"] = Response(
        200, b"<html>late</html>", {"Content-Type": "text/html"}, delay=1.5
    )
    site.page("/big", "Big", "<p>" + "word " * 10_000 + "</p>")
    job, pages = await run_crawl(site, project, timeout_seconds=1)
    assert pages["/slow"].fetch_status == FetchStatus.ERROR
    assert pages["/slow"].error == "Request timed out"
    assert pages["/big"].fetch_status == FetchStatus.TOO_LARGE
    assert job.pages_failed == 2


async def test_politeness_delay_between_requests(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    await run_crawl(site, project, max_pages=4, delay_ms=150, concurrency=3)
    starts = sorted(r.at for r in site.requests)
    gaps = [b - a for a, b in pairwise(starts)]
    # Times are when requests reach the fixture server, which can note one late when the
    # machine is busy and so shorten the following gap. Without a delay, concurrent
    # requests arrive together (gaps near zero), so these bounds still prove the delay.
    assert gaps and min(gaps) >= 0.1
    assert (starts[-1] - starts[0]) / len(gaps) >= 0.14


async def test_crawl_delay_from_robots_is_respected(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    site.routes["/robots.txt"] = Response(
        200, b"User-agent: *\nCrawl-delay: 0.3\n", {"Content-Type": "text/plain"}
    )
    await run_crawl(site, project, max_pages=3)
    starts = sorted(r.at for r in site.requests if r.path != "/robots.txt")
    gaps = [b - a for a, b in pairwise(starts)]
    assert gaps and min(gaps) >= 0.28


async def test_incremental_recrawl_uses_conditional_requests(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    first, first_pages = await run_crawl(site, project)
    site.requests.clear()
    site.page("/about", "About v2", "<h1>About</h1><p>Changed</p><a href='/'>Home</a>")
    second, pages = await run_crawl(site, project, previous=first.id)
    assert second.status == CrawlStatus.COMPLETED
    assert pages["/"].fetch_status == FetchStatus.NOT_MODIFIED
    assert pages["/"].title == "Home" and pages["/"].status_code == 200
    assert pages["/about"].fetch_status == FetchStatus.FETCHED
    assert pages["/about"].title == "About v2"
    home_request = next(r for r in site.requests if r.path == "/")
    assert home_request.headers.get("If-None-Match") == first_pages["/"].etag
    # Links of unchanged pages are carried over, so discovery still works.
    assert "/deep/1" in pages


async def test_cancellation_stops_the_crawl(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    for i in range(1, 8):
        site.routes[f"/deep/{i}"].delay = 0.4
    org_id, project_id = project
    config = CrawlConfig(
        root_url=f"{site.base}/",
        allowed_hosts=["127.0.0.1"],
        max_pages=100,
        max_depth=10,
        concurrency=1,
        timeout_seconds=5,
        delay_ms=0,
        user_agent=UA,
        extra_ports=[site.port],
    )
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=org_id,
            project_id=project_id,
            status=CrawlStatus.RUNNING,
            config=config.model_dump(),
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    task = asyncio.create_task(CrawlEngine(job_id, policy=policy_for(site)).run())
    await asyncio.sleep(1.2)
    async with get_session_factory()() as session:
        running = await session.get(CrawlJob, job_id)
        assert running is not None and running.pages_crawled > 0  # progress is visible
        running.status = CrawlStatus.CANCELLING
        await session.commit()
    status = await asyncio.wait_for(task, timeout=10)
    assert status == CrawlStatus.CANCELLED
    assert "/deep/7" not in site.paths()


async def test_loopback_is_blocked_without_an_explicit_allowance(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    config = CrawlConfig(
        root_url=f"{site.base}/",
        allowed_hosts=["127.0.0.1"],
        max_pages=10,
        max_depth=2,
        concurrency=1,
        timeout_seconds=2,
        delay_ms=0,
        user_agent=UA,
        extra_ports=[site.port],
    )
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=org_id,
            project_id=project_id,
            status=CrawlStatus.RUNNING,
            config=config.model_dump(),
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    # Default policy from settings: no private networks allowed.
    await CrawlEngine(job_id).run()
    async with get_session_factory()() as session:
        pages = list(
            await session.scalars(select(CrawlPage).where(CrawlPage.crawl_job_id == job_id))
        )
        job = await session.get(CrawlJob, job_id)
    assert site.requests == []
    assert job is not None and job.robots_status == "unreachable"
    assert all(p.fetch_status != FetchStatus.FETCHED for p in pages)


async def test_storage_failure_fails_the_crawl_instead_of_completing(
    site: FixtureSite, project, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    org_id, project_id = project
    config = CrawlConfig(
        root_url=f"{site.base}/",
        allowed_hosts=["127.0.0.1"],
        max_pages=5,
        max_depth=1,
        concurrency=1,
        timeout_seconds=2,
        delay_ms=0,
        user_agent=UA,
        extra_ports=[site.port],
    )
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=org_id,
            project_id=project_id,
            status=CrawlStatus.RUNNING,
            config=config.model_dump(),
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    engine = CrawlEngine(job_id, policy=policy_for(site))

    async def broken_save(page: CrawlPage, links: list[CrawlLink]) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(engine, "_save", broken_save)
    with pytest.raises(RuntimeError, match="could not be stored"):
        await engine.run()


async def test_a_start_page_that_answers_an_error_is_explained(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    site.routes["/"] = Response(403, b"Forbidden", {"Content-Type": "text/html"})
    del site.routes["/sitemap.xml"]
    job, pages = await run_crawl(site, project)
    assert len(pages) == 1
    assert job.warnings[0].startswith("The start page answered HTTP 403")


async def test_a_start_page_blocked_by_robots_is_explained(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    site.routes["/robots.txt"] = Response(
        200, b"User-agent: *\nDisallow: /\n", {"Content-Type": "text/plain"}
    )
    job, pages = await run_crawl(site, project)
    assert pages["/"].fetch_status == FetchStatus.BLOCKED_BY_ROBOTS
    assert "does not allow this crawler" in job.warnings[0] and UA in job.warnings[0]


async def test_a_start_address_redirecting_off_site_is_explained(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    elsewhere = f"http://localhost:{site.port}/"
    site.routes["/"] = Response(301, b"", {"Location": elsewhere})
    job, pages = await run_crawl(site, project)
    assert pages["/"].fetch_status == FetchStatus.REDIRECT_OUT_OF_SCOPE
    assert f"redirects to {elsewhere}" in job.warnings[0]
    assert "allowed extra hosts" in job.warnings[0]


async def test_a_start_page_with_almost_no_links_suggests_rendering(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    site.page("/", "Home", "<div id='app'></div><a href='/about'>About</a>")
    del site.routes["/sitemap.xml"]
    job, pages = await run_crawl(site, project)
    assert len(pages) <= 3  # the start page, /about and the one page /about links to
    assert job.warnings[0].startswith("The start page has only 1 link")
    assert "turn on JavaScript rendering" in job.warnings[0]


async def test_a_healthy_start_page_adds_no_explanation(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    job, _ = await run_crawl(site, project)
    assert not any("start page" in w or "start address" in w for w in job.warnings)


async def test_crawl_scope_includes_the_sites_www_name(project) -> None:  # type: ignore[no-untyped-def]
    from app.modules.crawler.service import build_config
    from app.modules.projects.models import Project

    _, project_id = project
    async with get_session_factory()() as session:
        p = await session.get(Project, project_id)
        assert p is not None
        p.root_url = "https://example.org/"
        assert (await build_config(session, p)).allowed_hosts == ["example.org", "www.example.org"]


async def test_a_sitemap_address_that_returns_a_web_page_is_explained(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    site.page("/sitemap.xml", "App", "<div id='app'></div>")
    job, _ = await run_crawl(site, project)
    assert "returns a web page, not a sitemap" in job.sitemaps[0]["error"]
