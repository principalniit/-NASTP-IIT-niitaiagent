"""crawl-check reports each step a crawl would take, and why it would stop."""

import pytest

from app.cli import crawl_check
from app.core.config import get_settings
from tests.fixtures.site import FixtureSite, Response, build_standard_site


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "crawler_allowed_private_networks", "127.0.0.1/32")
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def test_a_crawlable_site(site: FixtureSite, capsys: pytest.CaptureFixture[str]) -> None:
    await crawl_check(f"{site.base}/")
    out = capsys.readouterr().out
    assert "2. robots.txt: found" in out and "3. Start page: HTTP 200" in out
    assert "Result: a crawl can start here" in out


async def test_a_blocked_start_page(site: FixtureSite) -> None:
    site.routes["/"] = Response(403, b"no", {"Content-Type": "text/html"})
    with pytest.raises(SystemExit, match="answered HTTP 403"):
        await crawl_check(f"{site.base}/")


async def test_unreachable_robots(site: FixtureSite) -> None:
    site.routes["/robots.txt"] = Response(503, b"down", {"Content-Type": "text/plain"})
    with pytest.raises(SystemExit, match="RFC 9309"):
        await crawl_check(f"{site.base}/")


async def test_private_addresses_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "crawler_allowed_private_networks", "")
    with pytest.raises(SystemExit, match="Only public websites"):
        await crawl_check("http://127.0.0.1/")


async def test_render_finds_links_built_by_scripts(
    site: FixtureSite, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import os

    path = os.environ.get("TEST_PDF_BROWSER_PATH", "")
    if not path:
        pytest.skip("No Chromium here (set TEST_PDF_BROWSER_PATH)")
    monkeypatch.setattr(get_settings(), "crawler_browser_path", path)
    site.page("/", "App", "<div id='app'></div><script src='/app.js'></script>")
    site.routes["/app.js"] = Response(
        200,
        b"for (const p of ['/a', '/b', '/c']) { const l = document.createElement('a');"
        b" l.href = p; l.textContent = p; document.getElementById('app').appendChild(l); }",
        {"Content-Type": "application/javascript"},
    )
    await crawl_check(f"{site.base}/", render=True)
    out = capsys.readouterr().out
    assert "4. Links to this site in the HTML: 0" in out
    assert "Links to this site after rendering: 3" in out
    assert "Result: a crawl can start here" in out
