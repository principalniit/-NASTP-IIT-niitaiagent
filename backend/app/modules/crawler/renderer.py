"""JavaScript rendering that never gives the browser its own network access.

Headless Chromium runs the page's scripts, but every request it makes is intercepted and
either refused or fetched by the crawler itself, through the same guarded HTTP client as
every other crawl request: the SSRF check on the resolved address, the crawl scope,
robots.txt for the resource's path, the per-host politeness delay and the size cap. The
browser only receives what the crawler fetched.

Defence in depth: Chromium is started with no DNS (every host maps to "not found") and a
proxy that refuses connections, so a request that escaped interception (a WebSocket, a
prefetch, a worker) still reaches nothing. Service workers are blocked, nothing is cached
between pages, no cookies persist, and only GET requests for documents, scripts and data
(fetch and XMLHttpRequest) are allowed; images, styles, fonts, media and frames are not
needed to read the rendered HTML and are refused.

Optional: it uses the same Playwright and Chromium as PDF export. Without them a crawl
continues with pages analysed as served, and says so in its warnings.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_TYPES = frozenset({"document", "script", "xhr", "fetch"})
MAX_SUBREQUESTS = 40
RENDER_TIMEOUT_MS = 20_000
SETTLE_TIMEOUT_MS = 3_000
MAX_RENDERED_BYTES = 5_000_000
# Unreachable on purpose; see the module docstring.
CHROMIUM_ARGS = [
    "--proxy-server=http://127.0.0.1:1",
    "--proxy-bypass-list=<-loopback>",
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--dns-prefetch-disable",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-first-run",
]
INSTALL_HINT = (
    "JavaScript rendering needs Chromium: run `uv sync --extra pdf` and "
    "`uv run playwright install chromium` in the backend folder, then restart the worker."
)


@dataclass(frozen=True)
class SubResponse:
    status: int
    content_type: str
    body: bytes


# (url, resource type) -> the crawler's response, or None when the request is refused.
SubFetch = Callable[[str, str], Awaitable[SubResponse | None]]


@dataclass
class RenderResult:
    html: str | None
    fetched: int = 0
    refused: int = 0
    error: str | None = None
    # The document's address after its scripts ran. Single-page sites often change it
    # with the History API or a #fragment (/ to /#/home) without loading a new page.
    final_url: str | None = None
    # A different page the scripts tried to load; it is refused and the result dropped.
    navigated_to: str | None = None


class RendererUnavailableError(Exception):
    """Chromium could not be started. The message is safe to show."""


def _sandbox() -> bool:
    return not (hasattr(os, "geteuid") and os.geteuid() == 0)


class Renderer:
    def __init__(self, browser_path: str | None, user_agent: str) -> None:
        self.browser_path = browser_path or None
        self.user_agent = user_agent
        self._playwright: Any = None
        self._browser: Any = None

    async def start(self) -> None:
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RendererUnavailableError(INSTALL_HINT) from exc
        self._playwright = await async_playwright().start()
        sandbox = _sandbox()
        try:
            try:
                self._browser = await self._playwright.chromium.launch(
                    executable_path=self.browser_path, chromium_sandbox=sandbox, args=CHROMIUM_ARGS
                )
            except PlaywrightError:
                if not sandbox:
                    raise
                logger.warning("Chromium's sandbox could not start; rendering without it")
                self._browser = await self._playwright.chromium.launch(
                    executable_path=self.browser_path, chromium_sandbox=False, args=CHROMIUM_ARGS
                )
        except PlaywrightError as exc:
            await self._playwright.stop()
            self._playwright = None
            logger.warning("Renderer could not start", extra={"error": str(exc)[:300]})
            raise RendererUnavailableError(INSTALL_HINT) from exc

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = self._playwright = None

    async def render(
        self, url: str, html: bytes, content_type: str, fetch: SubFetch
    ) -> RenderResult:
        """Run the page's scripts on the HTML the crawler already fetched."""
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        result = RenderResult(html=None)
        if self._browser is None:
            result.error = "The renderer is not running"
            return result
        context = await self._browser.new_context(
            user_agent=self.user_agent,
            service_workers="block",
            accept_downloads=False,
            java_script_enabled=True,
        )
        lock = asyncio.Lock()
        served: list[str] = []

        async def handle(route: Any) -> None:
            request = route.request
            if request.resource_type == "document" and request.is_navigation_request():
                main = request.frame.parent_frame is None
                if main and request.url == url and not served:
                    # The document itself is the response the crawler already has.
                    served.append(url)
                    await route.fulfill(
                        status=200, content_type=content_type or "text/html", body=html
                    )
                    return
                if main and result.navigated_to is None:
                    result.navigated_to = request.url
            async with lock:
                allowed = (
                    request.method == "GET"
                    and request.resource_type in ALLOWED_TYPES
                    and request.resource_type != "document"
                    and request.url.startswith(("http://", "https://"))
                    and result.fetched + result.refused < MAX_SUBREQUESTS
                )
            response = await fetch(request.url, request.resource_type) if allowed else None
            async with lock:
                if response is None:
                    result.refused += 1
                else:
                    result.fetched += 1
            if response is None:
                await route.abort("blockedbyclient")
            else:
                await route.fulfill(
                    status=response.status, content_type=response.content_type, body=response.body
                )

        try:
            page = await context.new_page()
            await page.route("**/*", handle)
            await page.goto(url, wait_until="load", timeout=RENDER_TIMEOUT_MS)
            # A page that keeps polling never goes idle; it is rendered all the same.
            with contextlib.suppress(PlaywrightTimeout):
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            if result.navigated_to is not None:
                # Loading another document is refused, so what remains is not this page.
                result.error = (
                    f"The page's scripts tried to open another page ({result.navigated_to})"
                )
                return result
            result.final_url = page.url
            rendered = await page.content()
            if len(rendered.encode()) > MAX_RENDERED_BYTES:
                result.error = "The rendered page is too large"
                return result
            result.html = rendered
        except Exception as exc:
            logger.info("Rendering failed", extra={"url": url, "error": type(exc).__name__})
            result.error = "The page could not be rendered in time"
        finally:
            await context.close()
        return result
