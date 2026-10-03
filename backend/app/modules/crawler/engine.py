"""Crawl orchestration: robots.txt, sitemaps, a polite breadth-first frontier,
persistence of pages and links, progress, cancellation and finalisation."""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import undefer

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.fetcher import Fetcher, FetchResult
from app.modules.crawler.models import (
    AnalysisStatus,
    CrawlJob,
    CrawlLink,
    CrawlPage,
    CrawlStatus,
    FetchStatus,
)
from app.modules.crawler.parser import (
    ParsedPage,
    hash_route_links,
    parse_html,
    robots_directives,
)
from app.modules.crawler.renderer import (
    Renderer,
    RendererUnavailableError,
    SubResponse,
)
from app.modules.crawler.robots import RobotsPolicy, RobotsTxt
from app.modules.crawler.sitemaps import SitemapError, parse_sitemap
from app.modules.crawler.url_safety import Resolver, SafetyPolicy, system_resolve
from app.modules.crawler.urls import host_of, is_excluded, normalise_url, path_with_query

logger = logging.getLogger(__name__)

FAILED_OUTCOMES = {
    "error": FetchStatus.ERROR,
    "too_large": FetchStatus.TOO_LARGE,
    "blocked_destination": FetchStatus.BLOCKED_DESTINATION,
}
# Page fields copied from the previous crawl when the server answers 304 Not Modified.
COPIED_FIELDS = (
    "status_code", "content_type", "content_length", "title", "title_count",
    "meta_description", "meta_description_count", "meta_robots", "x_robots_tag",
    "is_noindex", "is_nofollow", "canonical_url", "canonical_count", "lang", "headings",
    "h1_count", "word_count", "content_hash", "text_content", "images", "image_count",
    "images_missing_alt",
    "structured_data", "hreflang", "internal_links_count", "external_links_count",
    "rendered_with_js",
)  # fmt: skip
# Sub-resources fetched for rendering: a smaller cap than pages, and scripts are cached
# for the whole crawl so a shared bundle is fetched once.
SUBRESOURCE_MAX_BYTES = 3_000_000
SCRIPT_CACHE_MAX_BYTES = 30_000_000


class HostThrottle:
    """Guarantees a minimum delay between request starts to the same host."""

    def __init__(self) -> None:
        self._next_allowed: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str, delay: float) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            pause = self._next_allowed.get(host, 0.0) - time.monotonic()
            if pause > 0:
                await asyncio.sleep(pause)
            self._next_allowed[host] = time.monotonic() + delay


@dataclass
class QueueItem:
    url: str
    depth: int | None  # None for pages found only in a sitemap
    via: str  # root | link | sitemap


def _now() -> datetime:
    return datetime.now(UTC)


class CrawlEngine:
    def __init__(
        self,
        job_id: uuid.UUID,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        policy: SafetyPolicy | None = None,
        resolver: Resolver = system_resolve,
    ) -> None:
        self.job_id = job_id
        self.factory = session_factory or get_session_factory()
        self._policy_override = policy
        self.resolver = resolver
        self.settings = get_settings()
        self.throttle = HostThrottle()
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.seen: set[str] = set()
        self.sitemap_urls: dict[str, None] = {}
        self.robots: dict[str, RobotsPolicy] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self.previous: dict[str, CrawlPage] = {}
        self.warnings: list[str] = []
        self.sitemap_log: list[dict[str, Any]] = []
        self.counts = {"crawled": 0, "failed": 0, "blocked": 0}
        self.stop_reason: str | None = None
        self.limit_reached = False
        self.renderer: Renderer | None = None
        self.render_failures = 0
        self.render_failure_reason: str | None = None
        self._script_cache: dict[str, SubResponse] = {}
        self._script_cache_bytes = 0
        # Why the crawl could not get past its start page, when it could not.
        self.start_problem: str | None = None
        self.start_links: int | None = None
        self.start_hash_links = 0

    # ------------------------------------------------------------------ helpers

    def _few_links_warning(self, count: int) -> str:
        if self.start_hash_links:
            hashed = self.start_hash_links
            return (
                f"The start page links to its other pages with #-addresses ({hashed} links "
                "such as #/about). Search engines treat everything after # as the same address, "
                "so to Google this site is a single page. Ask its developer to give each page a "
                "real address (History API routing) and to serve its content without "
                "JavaScript (server-side rendering or prerendering)."
            )
        found = "no links" if count == 0 else f"only {count} link{'s' if count > 1 else ''}"
        if self.config.render_javascript:
            return (
                f"The start page has {found} to other pages on this site, even with JavaScript "
                "rendering, so little could be crawled. Add the site's sitemap, or check that "
                "its pages link to each other."
            )
        return (
            f"The start page has {found} to other pages on this site in its HTML, so little "
            "could be crawled. If the site builds its menus with JavaScript, turn on JavaScript "
            "rendering in the project's crawl settings and crawl again."
        )

    def in_scope(self, url: str) -> bool:
        return host_of(url) in self.allowed_hosts

    def _can_enqueue(self, url: str) -> bool:
        return (
            url not in self.seen
            and self.in_scope(url)
            and not is_excluded(url, self.config.excluded_paths)
        )

    def _claim_budget(self, url: str) -> bool:
        """Reserve a page slot for url. Returns False when the page limit is reached."""
        if len(self.seen) >= self.config.max_pages:
            self.limit_reached = True
            return False
        self.seen.add(url)
        return True

    def _enqueue(self, url: str, depth: int | None, via: str) -> None:
        if self._can_enqueue(url) and self._claim_budget(url):
            self.queue.put_nowait(QueueItem(url, depth, via))

    async def _host_delay(self, host: str) -> float:
        robots = await self._robots_for(host)
        delay = self.config.delay_ms / 1000
        crawl_delay = robots.crawl_delay(self.config.user_agent)
        return max(delay, crawl_delay or 0.0)

    async def _wait_turn(self, url: str) -> None:
        host = host_of(url)
        await self.throttle.wait(host, await self._host_delay(host))

    async def _fetch(self, url: str, **kwargs: Any) -> FetchResult:
        return await self.fetcher.fetch(
            url, in_scope=self.in_scope, before_request=self._wait_turn, **kwargs
        )

    async def _sub_fetch(self, url: str, resource_type: str) -> SubResponse | None:
        """Fetch a resource a page's scripts asked for, under every crawl safeguard:
        crawl scope, exclusions, robots.txt, politeness, the SSRF guard and a size cap."""
        target = normalise_url(url)
        if target is None or not self.in_scope(target):
            return None
        if is_excluded(target, self.config.excluded_paths):
            return None
        cached = self._script_cache.get(target)
        if cached is not None:
            return cached
        robots = await self._robots_for(host_of(target))
        if not robots.can_fetch(self.config.user_agent, path_with_query(target)):
            return None
        result = await self._fetch(
            target, read_body=lambda _: True, max_bytes=SUBRESOURCE_MAX_BYTES
        )
        if result.outcome != "ok" or result.status_code is None:
            return None
        response = SubResponse(
            result.status_code,
            result.headers.get("content-type", "application/octet-stream"),
            result.body or b"",
        )
        size = len(response.body)
        if resource_type == "script" and self._script_cache_bytes + size <= SCRIPT_CACHE_MAX_BYTES:
            self._script_cache[target] = response
            self._script_cache_bytes += size
        return response

    async def _start_renderer(self) -> None:
        renderer = Renderer(
            self.settings.crawler_browser_path or self.settings.report_pdf_browser_path,
            self.config.user_agent,
        )
        try:
            await renderer.start()
        except RendererUnavailableError as exc:
            self.warnings.append(
                f"JavaScript rendering was requested but is not available: {exc} Pages were "
                "analysed as served, without running scripts."
            )
            return
        self.renderer = renderer

    # ------------------------------------------------------------------ robots and sitemaps

    async def _robots_for(self, host: str) -> RobotsPolicy:
        if host in self.robots:
            return self.robots[host]
        lock = self._robots_locks.setdefault(host, asyncio.Lock())
        async with lock:
            if host in self.robots:
                return self.robots[host]
            scheme = urlsplit(self.config.root_url).scheme
            port = urlsplit(self.config.root_url).port if host == self.root_host else None
            netloc = f"{host}:{port}" if port else host
            url = f"{scheme}://{netloc}/robots.txt"
            result = await self.fetcher.fetch(
                url,
                in_scope=lambda u: host_of(u) == host,
                read_body=lambda _: True,
                before_request=lambda u: self.throttle.wait(host, self.config.delay_ms / 1000),
            )
            if result.outcome == "ok" and result.status_code and 200 <= result.status_code < 300:
                body = (result.body or b"").decode("utf-8", errors="replace")
                policy = RobotsPolicy("found", RobotsTxt.parse(body))
            elif result.outcome == "ok" and result.status_code and 400 <= result.status_code < 500:
                policy = RobotsPolicy("not_found")
            elif result.outcome == "redirect_out_of_scope":
                policy = RobotsPolicy("not_found")
                self.warnings.append(f"robots.txt on {host} redirects to another host; ignored.")
            else:
                policy = RobotsPolicy("unreachable")
                self.warnings.append(
                    f"robots.txt on {host} could not be fetched "
                    f"({result.error or result.status_code}); as required by RFC 9309 no "
                    "pages on this host were crawled."
                )
            self.robots[host] = policy
            return policy

    async def _load_sitemaps(self) -> None:
        robots = await self._robots_for(self.root_host)
        root = urlsplit(self.config.root_url)
        pending = [u for u in (normalise_url(s) for s in robots.sitemaps) if u]
        if not pending:
            pending = [f"{root.scheme}://{root.netloc}/sitemap.xml"]
        fetched = 0
        visited: set[str] = set()
        while pending and fetched < self.settings.crawler_max_sitemaps:
            url = pending.pop(0)
            if url in visited:
                continue
            visited.add(url)
            entry: dict[str, Any] = {"url": url, "status": "error", "url_count": 0, "error": None}
            self.sitemap_log.append(entry)
            if not self.in_scope(url):
                entry.update(status="skipped", error="Sitemap is on a host outside the crawl scope")
                continue
            fetched += 1
            result = await self._fetch(
                url, read_body=lambda _: True, max_bytes=self.settings.crawler_max_sitemap_bytes
            )
            if result.outcome != "ok" or not result.status_code or result.status_code >= 400:
                entry.update(
                    status="not_found" if result.status_code == 404 else "error",
                    error=result.error or f"HTTP {result.status_code}",
                )
                continue
            if result.is_html:
                # Single-page sites often answer every address, sitemap.xml included, with
                # the app's own page. Search engines get no sitemap from it either.
                entry["error"] = (
                    "The sitemap address returns a web page, not a sitemap. Search engines "
                    "cannot read it either; the site should serve a real XML sitemap here."
                )
                continue
            try:
                content = parse_sitemap(result.body or b"")
            except SitemapError as exc:
                entry["error"] = str(exc)
                continue
            entry["status"] = "ok"
            if content.kind == "index":
                entry["kind"] = "index"
                pending.extend(u for u in (normalise_url(s) for s in content.sitemaps) if u)
                continue
            for loc in content.urls:
                normalised = normalise_url(loc)
                if normalised and self.in_scope(normalised):
                    self.sitemap_urls.setdefault(normalised, None)
                    entry["url_count"] += 1
        if pending:
            self.warnings.append(
                f"Only the first {self.settings.crawler_max_sitemaps} sitemap files were read."
            )

    # ------------------------------------------------------------------ page processing

    async def _process(self, item: QueueItem) -> None:
        robots = await self._robots_for(host_of(item.url))
        if not robots.can_fetch(self.config.user_agent, path_with_query(item.url)):
            if item.via == "root" and robots.status != "unreachable":
                self.start_problem = (
                    f"robots.txt on {host_of(item.url)} does not allow this crawler "
                    f"({self.config.user_agent}) to fetch the start page, so no links could be "
                    "followed. Only the site owner can allow it."
                )
            self.counts["blocked"] += 1
            await self._save(self._page(item, FetchStatus.BLOCKED_BY_ROBOTS), [])
            return
        previous = self.previous.get(item.url)
        conditional: dict[str, str] = {}
        if previous is not None and previous.etag:
            conditional["If-None-Match"] = previous.etag
        if previous is not None and previous.last_modified:
            conditional["If-Modified-Since"] = previous.last_modified
        result = await self._fetch(item.url, conditional=conditional or None)

        if result.outcome in FAILED_OUTCOMES:
            if item.via == "root":
                self.start_problem = _start_failure(result)
            self.counts["failed"] += 1
            page = self._page(item, FAILED_OUTCOMES[result.outcome], result)
            await self._save(page, [])
            return

        if result.redirect_chain:
            first = result.redirect_chain[0]
            redirect = self._page(item, FetchStatus.FETCHED, result)
            redirect.status_code = first["status_code"]
            redirect.response_time_ms = first["elapsed_ms"]
            redirect.content_type = None
            if result.outcome == "redirect_out_of_scope":
                redirect.fetch_status = FetchStatus.REDIRECT_OUT_OF_SCOPE
                if item.via == "root":
                    self.start_problem = (
                        f"The start address redirects to {result.final_url}, which is outside "
                        "this project's site, so nothing else was crawled. Change the project "
                        "address to that site, or add its host to the allowed extra hosts in "
                        "the project settings."
                    )
            self.counts["crawled"] += 1
            await self._save(redirect, [])
            target = result.final_url
            if (
                result.outcome == "redirect_out_of_scope"
                or target is None
                or not self._can_enqueue(target)
                or not self._claim_budget(target)
            ):
                return
            item = QueueItem(target, item.depth, item.via)
            result.redirect_chain = []
            previous = None

        await self._record_response(item, result, previous)

    async def _record_response(
        self, item: QueueItem, result: FetchResult, previous: CrawlPage | None
    ) -> None:
        page = self._page(item, FetchStatus.FETCHED, result)
        links: list[CrawlLink] = []
        extracted: list[tuple[str, bool]] = []
        if result.outcome == "not_modified" and previous is not None:
            page.fetch_status = FetchStatus.NOT_MODIFIED
            for name in COPIED_FIELDS:
                setattr(page, name, getattr(previous, name))
            async with self.factory() as session:
                rows = await session.scalars(
                    select(CrawlLink).where(CrawlLink.source_page_id == previous.id)
                )
                for old in rows:
                    links.append(self._link(page, old.target_url, old.anchor_text, old.nofollow))
                    extracted.append((old.target_url, old.nofollow))
        elif result.status_code and 200 <= result.status_code < 300 and result.is_html:
            body = result.body or b""
            # Links resolve against the address the page's scripts left it at, as in a
            # browser (a single-page site may move / to /home without loading a page).
            base = result.final_url or item.url
            if self.renderer is not None:
                rendered = await self.renderer.render(
                    result.final_url or item.url, body, result.content_type, self._sub_fetch
                )
                if rendered.html is not None:
                    body = rendered.html.encode()
                    page.rendered_with_js = True
                    base = rendered.final_url or base
                else:
                    self.render_failures += 1
                    self.render_failure_reason = self.render_failure_reason or rendered.error
            parsed = parse_html(body, base)
            self._apply_parsed(page, parsed, result)
            for link in parsed.links:
                links.append(self._link(page, link.url, link.anchor_text, link.nofollow))
                extracted.append((link.url, link.nofollow))
            if item.via == "root":
                # Other pages it links to: #-links of a single-page site all resolve to
                # this page itself, so they do not count.
                targets = {link.url for link in parsed.links if self.in_scope(link.url)}
                self.start_links = len(targets - {item.url, base})
                self.start_hash_links = hash_route_links(body)
        elif result.status_code and 200 <= result.status_code < 300:
            page.fetch_status = FetchStatus.SKIPPED_CONTENT_TYPE
            if item.via == "root":
                kind = result.content_type or "unknown type"
                self.start_problem = (
                    f"The start page is not an HTML page ({kind}), so it has no links to follow."
                )
        elif item.via == "root" and result.status_code and result.status_code >= 400:
            self.start_problem = (
                f"The start page answered HTTP {result.status_code}, so no links could be "
                "followed. The site may be down, need a login, or refuse automated crawlers; "
                "only the site owner can allow this crawler."
            )
        self.counts["crawled"] += 1
        await self._save(page, links)
        # Links on sitemap-only pages are recorded but not followed, which keeps the
        # crawl bounded by link depth from the root.
        if item.depth is not None and item.depth < self.config.max_depth:
            for url, _ in extracted:
                self._enqueue(url, item.depth + 1, "link")

    def _apply_parsed(self, page: CrawlPage, parsed: ParsedPage, result: FetchResult) -> None:
        directives = robots_directives(parsed.meta_robots) | robots_directives(
            result.headers.get("x-robots-tag")
        )
        page.title = parsed.title
        page.title_count = parsed.title_count
        page.meta_description = parsed.meta_description
        page.meta_description_count = parsed.meta_description_count
        page.meta_robots = parsed.meta_robots
        page.is_noindex = bool(directives & {"noindex", "none"})
        page.is_nofollow = bool(directives & {"nofollow", "none"})
        page.canonical_url = parsed.canonical_url
        page.canonical_count = parsed.canonical_count
        page.lang = parsed.lang
        page.headings = parsed.headings
        page.h1_count = parsed.h1_count
        page.word_count = parsed.word_count
        page.content_hash = parsed.content_hash
        page.text_content = parsed.text or None
        page.images = parsed.images
        page.image_count = parsed.image_count
        page.images_missing_alt = parsed.images_missing_alt
        page.structured_data = parsed.structured_data
        page.hreflang = parsed.hreflang
        page.internal_links_count = sum(1 for link in parsed.links if self.in_scope(link.url))
        page.external_links_count = len(parsed.links) - page.internal_links_count

    def _page(
        self, item: QueueItem, status: FetchStatus, result: FetchResult | None = None
    ) -> CrawlPage:
        page = CrawlPage(
            id=uuid.uuid4(),
            organisation_id=self.organisation_id,
            crawl_job_id=self.job_id,
            url=item.url,
            depth=item.depth,
            discovered_via=item.via,
            fetch_status=status,
            in_sitemap=item.url in self.sitemap_urls,
            fetched_at=_now(),
        )
        if result is not None:
            length = result.headers.get("content-length", "")
            page.final_url = result.final_url
            page.status_code = result.status_code
            page.error = result.error
            page.content_type = result.content_type or None
            page.response_time_ms = result.elapsed_ms
            page.content_length = (
                len(result.body)
                if result.body is not None
                else (int(length) if length.isdigit() else None)
            )
            page.redirect_chain = result.redirect_chain
            page.etag = result.headers.get("etag", "")[:300] or None
            page.last_modified = result.headers.get("last-modified", "")[:100] or None
            page.x_robots_tag = result.headers.get("x-robots-tag", "")[:300] or None
        return page

    def _link(self, page: CrawlPage, target: str, anchor: str | None, nofollow: bool) -> CrawlLink:
        return CrawlLink(
            organisation_id=self.organisation_id,
            crawl_job_id=self.job_id,
            source_page_id=page.id,
            target_url=target,
            is_internal=self.in_scope(target),
            nofollow=nofollow,
            anchor_text=(anchor or None),
        )

    async def _save(self, page: CrawlPage, links: list[CrawlLink]) -> None:
        async with self.factory() as session:
            session.add(page)
            await session.flush()
            session.add_all(links)
            await session.commit()

    # ------------------------------------------------------------------ run loop

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if self.stop_reason is None:
                    await self._process(item)
            except Exception:
                logger.exception("Error while processing %s", item.url)
                self.counts["failed"] += 1
                page = self._page(item, FetchStatus.ERROR)
                page.error = "Internal error while processing this page"
                try:
                    await self._save(page, [])
                except Exception:
                    # Results cannot be stored at all: stop rather than report a
                    # misleading "completed" crawl.
                    logger.exception("Could not record failed page %s", item.url)
                    self.stop_reason = "internal_error"
            finally:
                self.queue.task_done()

    async def _flush_progress(self) -> None:
        async with self.factory() as session:
            job = await session.get(CrawlJob, self.job_id)
            if job is None:
                self.stop_reason = "deleted"
                return
            if job.status == CrawlStatus.CANCELLING:
                self.stop_reason = "cancelled"
            job.pages_discovered = len(self.seen)
            job.pages_crawled = self.counts["crawled"]
            job.pages_failed = self.counts["failed"]
            job.pages_blocked = self.counts["blocked"]
            job.heartbeat_at = _now()
            await session.commit()

    async def _monitor(self) -> None:
        started = time.monotonic()
        failures = 0
        while True:
            await asyncio.sleep(1.0)
            try:
                await self._flush_progress()
                failures = 0
            except Exception:
                failures += 1
                logger.exception("Could not record crawl progress")
                if failures >= 3:
                    self.stop_reason = "internal_error"
            if time.monotonic() - started > self.settings.crawler_max_duration_seconds:
                self.stop_reason = self.stop_reason or "time_limit"

    async def run(self) -> CrawlStatus:
        async with self.factory() as session:
            job = await session.get(CrawlJob, self.job_id)
            if job is None:
                raise LookupError(f"Crawl job {self.job_id} not found")
            self.organisation_id = job.organisation_id
            self.config = CrawlConfig.model_validate(job.config)
            if job.incremental and job.previous_crawl_id:
                rows = await session.scalars(
                    select(CrawlPage)
                    .options(undefer(CrawlPage.text_content))
                    .where(CrawlPage.crawl_job_id == job.previous_crawl_id)
                )
                self.previous = {p.url: p for p in rows}
        self.root_host = host_of(self.config.root_url)
        self.allowed_hosts = set(self.config.allowed_hosts)
        policy = self._policy_override or SafetyPolicy.from_settings(self.config.extra_ports)
        self.fetcher = Fetcher(
            user_agent=self.config.user_agent,
            timeout_seconds=self.config.timeout_seconds,
            max_bytes=self.settings.crawler_max_response_bytes,
            max_redirects=self.settings.crawler_max_redirects,
            policy=policy,
            resolver=self.resolver,
            max_connections=self.config.concurrency * 2,
        )
        if self.config.render_javascript:
            await self._start_renderer()
        monitor = asyncio.create_task(self._monitor())
        workers = [asyncio.create_task(self._worker()) for _ in range(self.config.concurrency)]
        try:
            await self._load_sitemaps()
            self._enqueue(self.config.root_url, 0, "root")
            await self.queue.join()
            # Pages listed only in sitemaps are crawled once link discovery is exhausted.
            for url in self.sitemap_urls:
                if self.stop_reason:
                    break
                self._enqueue(url, None, "sitemap")
            await self.queue.join()
        finally:
            for task in (*workers, monitor):
                task.cancel()
            await asyncio.gather(*workers, monitor, return_exceptions=True)
            if self.renderer is not None:
                await self.renderer.close()
            await self.fetcher.aclose()
        if self.render_failures:
            self.warnings.append(
                f"{self.render_failures} page(s) could not be rendered with JavaScript and were "
                f"analysed as served. First reason: {self.render_failure_reason or 'unknown'}."
            )
        if self.stop_reason == "internal_error":
            raise RuntimeError("Crawl results could not be stored")
        return await self._finalise()

    async def _finalise(self) -> CrawlStatus:
        params = {"job": self.job_id}
        async with self.factory() as session:
            await session.execute(
                text(
                    "UPDATE crawl_links l SET target_page_id = p.id FROM crawl_pages p "
                    "WHERE l.crawl_job_id = :job AND p.crawl_job_id = :job AND p.url = l.target_url"
                ),
                params,
            )
            await session.execute(
                text(
                    "UPDATE crawl_pages p SET inlinks_count = s.n FROM ("
                    " SELECT target_page_id, count(DISTINCT source_page_id) AS n FROM crawl_links"
                    " WHERE crawl_job_id = :job AND is_internal AND target_page_id IS NOT NULL"
                    " AND target_page_id <> source_page_id GROUP BY target_page_id) s "
                    "WHERE p.id = s.target_page_id"
                ),
                params,
            )
            if self.start_problem:
                self.warnings.insert(0, self.start_problem)
            elif self.start_links is not None and self.start_links < 3 and len(self.seen) <= 3:
                self.warnings.insert(0, self._few_links_warning(self.start_links))
            if self.limit_reached:
                self.warnings.append(
                    f"The page limit ({self.config.max_pages}) was reached before the whole site "
                    "was crawled. Orphan pages were not identified because unvisited pages may "
                    "link to them."
                )
            elif self.stop_reason is None:
                await session.execute(
                    update(CrawlPage)
                    .where(
                        CrawlPage.crawl_job_id == self.job_id,
                        CrawlPage.in_sitemap.is_(True),
                        CrawlPage.inlinks_count == 0,
                        CrawlPage.url != self.config.root_url,
                        CrawlPage.fetch_status.in_([FetchStatus.FETCHED, FetchStatus.NOT_MODIFIED]),
                    )
                    .values(is_orphan=True)
                )
            if self.stop_reason == "time_limit":
                self.warnings.append("The crawl stopped at the maximum crawl duration.")
            job = await session.get(CrawlJob, self.job_id)
            if job is None:
                return CrawlStatus.FAILED
            job.status = (
                CrawlStatus.CANCELLED if self.stop_reason == "cancelled" else CrawlStatus.COMPLETED
            )
            if job.status == CrawlStatus.COMPLETED:
                # Cancelled crawls are not analysed: partial data would wrongly resolve issues.
                job.analysis_status = AnalysisStatus.QUEUED
            job.pages_discovered = len(self.seen)
            job.pages_crawled = self.counts["crawled"]
            job.pages_failed = self.counts["failed"]
            job.pages_blocked = self.counts["blocked"]
            job.robots_status = self.robots.get(self.root_host, RobotsPolicy("unreachable")).status
            job.sitemaps = self.sitemap_log
            job.sitemap_url_count = len(self.sitemap_urls)
            job.warnings = self.warnings
            job.finished_at = _now()
            job.heartbeat_at = job.finished_at
            await session.commit()
            return job.status


def _start_failure(result: FetchResult) -> str:
    if result.outcome == "blocked_destination":
        return (
            "The start address points to a private or reserved network address, which the "
            "crawler refuses for safety. Only public websites can be crawled."
        )
    if result.outcome == "too_large":
        return "The start page is larger than the crawler's size limit, so it was not read."
    return (
        f"The start page could not be fetched ({result.error or 'no response'}). Check the "
        "address and that the site is up, then crawl again."
    )


EngineFactory = Callable[[uuid.UUID], CrawlEngine]
