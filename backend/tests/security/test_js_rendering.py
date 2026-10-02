"""JavaScript rendering: pages are analysed after their scripts run, and the browser never
reaches the network itself. Every request it makes is refused or fetched by the crawler
under the SSRF guard, crawl scope and robots.txt."""

import json
import os
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.crawler.models import CrawlJob, CrawlPage
from app.worker import process_next_job
from tests.fixtures.site import FixtureSite, Response
from tests.integration.test_crawl_api import engine_for, setup


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> str:
    path = os.environ.get("TEST_PDF_BROWSER_PATH", "")
    if not path:
        pytest.skip("No Chromium here (set TEST_PDF_BROWSER_PATH)")
    monkeypatch.setattr(get_settings(), "crawler_browser_path", path)
    return path


@pytest.fixture
def outside() -> Iterator[FixtureSite]:
    """Another site, outside the crawl scope, that must never be contacted."""
    with FixtureSite() as s:
        s.page("/secret", "Secret", "<p>internal</p>")
        yield s


@pytest.fixture
def site(outside: FixtureSite) -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        s.routes["/robots.txt"] = Response(
            200, b"User-agent: *\nDisallow: /private/\n", {"Content-Type": "text/plain"}
        )
        s.page(
            "/",
            "Home",
            "<div id='app'></div><a href='/static'>Static</a>"
            "<script src='/app.js'></script><script src='/private/tracker.js'></script>",
        )
        script = (
            "fetch('/data.json').then(r => r.json()).then(d => {"
            "  document.getElementById('app').innerHTML ="
            "    '<h1>' + d.heading + '</h1><p>' + d.text + '</p><a href=\"/from-js\">More</a>';"
            "});"
            f"fetch('{outside.base}/secret').catch(() => {{}});"
            "fetch('http://169.254.169.254/latest/meta-data/').catch(() => {});"
            "new Image().src = '/pixel.png';"
            # Interception does not see WebSockets; the browser's dead proxy must stop them.
            f"try {{ new WebSocket('ws://127.0.0.1:{outside.port}/ws'); }} catch (e) {{}}"
        )
        s.routes["/app.js"] = Response(
            200, script.encode(), {"Content-Type": "application/javascript"}
        )
        s.routes["/private/tracker.js"] = Response(
            200, b"document.title = 'tracked';", {"Content-Type": "application/javascript"}
        )
        s.routes["/data.json"] = Response(
            200,
            json.dumps(
                {"heading": "Rendered heading", "text": "Words that only scripts write."}
            ).encode(),
            {"Content-Type": "application/json"},
        )
        s.page("/static", "Static", "<h1>Static</h1>")
        s.page("/from-js", "From JS", "<h1>Found through a script</h1>")
        yield s


async def _crawl(client: AsyncClient, site: FixtureSite, render: bool) -> dict[str, CrawlPage]:
    owner, _, project = await setup(client, site)
    url = f"/api/v1/projects/{project['id']}/settings"
    settings = (await client.get(url, headers=owner.headers)).json()["settings"]
    settings["crawl"]["render_javascript"] = render
    assert (await client.put(url, json=settings, headers=owner.headers)).status_code == 200
    started = await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    assert started.status_code == 201, started.text
    await process_next_job("w", engine_factory=engine_for(site))
    async with get_session_factory()() as session:
        rows = await session.scalars(select(CrawlPage))
        return {p.url.removeprefix(site.base): p for p in rows}


async def test_pages_are_analysed_after_their_scripts_run(
    client: AsyncClient, site: FixtureSite, outside: FixtureSite, browser: str
) -> None:
    pages = await _crawl(client, site, render=True)
    home = pages["/"]
    assert home.rendered_with_js and home.h1_count == 1
    assert {"level": 1, "text": "Rendered heading"} in home.headings
    assert "/from-js" in pages, "a link written by a script is followed"
    assert home.title == "Home", "a robots.txt-blocked script never ran"

    paths = site.paths()
    assert "/app.js" in paths and "/data.json" in paths
    assert "/private/tracker.js" not in paths, "robots.txt applies to scripts"
    assert "/pixel.png" not in paths, "images are not fetched for rendering"
    assert outside.paths() == [], "nothing outside the crawl scope is contacted"
    # Every request came from the crawler's own client, not from the browser.
    assert all("Sec-Fetch-Mode" not in r.headers for r in site.requests)
    assert all(r.user_agent == site.requests[0].user_agent for r in site.requests)


async def test_without_the_setting_pages_are_analysed_as_served(
    client: AsyncClient, site: FixtureSite, browser: str
) -> None:
    pages = await _crawl(client, site, render=False)
    assert not pages["/"].rendered_with_js and pages["/"].h1_count == 0
    assert "/from-js" not in pages
    assert "/app.js" not in site.paths()


async def test_a_crawl_continues_when_no_browser_is_available(
    client: AsyncClient, site: FixtureSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "crawler_browser_path", "/nonexistent/chromium")
    pages = await _crawl(client, site, render=True)
    assert not pages["/"].rendered_with_js and "/static" in pages
    async with get_session_factory()() as session:
        job = await session.scalar(select(CrawlJob))
        assert job is not None and job.status == "completed"
        assert any(
            "JavaScript rendering was requested but is not available" in w for w in job.warnings
        )
