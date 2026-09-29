"""Everything a rule may look at, loaded once from the database for one crawl.

Rules are pure functions of this context, so they are deterministic and testable
without a database or network.
"""

import fnmatch
import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.models import FetchStatus
from app.modules.crawler.urls import normalise_url
from app.modules.projects.schemas import ProjectSettingsData

HTML_TYPES = ("text/html", "application/xhtml+xml")
RESPONDED = (FetchStatus.FETCHED, FetchStatus.NOT_MODIFIED)


@dataclass
class PageData:
    id: uuid.UUID
    url: str
    fetch_status: FetchStatus
    status_code: int | None = None
    final_url: str | None = None
    depth: int | None = None
    discovered_via: str = "link"
    content_type: str | None = "text/html"
    error: str | None = None
    response_time_ms: int | None = None
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    title: str | None = None
    title_count: int = 0
    meta_description: str | None = None
    meta_description_count: int = 0
    meta_robots: str | None = None
    x_robots_tag: str | None = None
    is_noindex: bool = False
    canonical_url: str | None = None
    canonical_count: int = 0
    lang: str | None = None
    headings: list[dict[str, Any]] = field(default_factory=list)
    h1_count: int = 0
    word_count: int | None = None
    content_hash: str | None = None
    text: str | None = None
    images: list[dict[str, Any]] = field(default_factory=list)
    image_count: int = 0
    images_missing_alt: int = 0
    structured_data: dict[str, Any] = field(default_factory=dict)
    internal_links_count: int = 0
    external_links_count: int = 0
    inlinks_count: int = 0
    in_sitemap: bool = False
    is_orphan: bool = False

    @property
    def analysable(self) -> bool:
        """A successfully fetched HTML page whose content was examined."""
        return (
            self.fetch_status in RESPONDED
            and self.status_code is not None
            and 200 <= self.status_code < 300
            and (self.content_type or "") in HTML_TYPES
        )

    @property
    def canonicalised_elsewhere(self) -> bool:
        return bool(self.canonical_url) and self.canonical_url != self.url

    @property
    def indexable(self) -> bool:
        return self.analysable and not self.is_noindex and not self.canonicalised_elsewhere

    @property
    def is_redirect(self) -> bool:
        return self.status_code is not None and 300 <= self.status_code < 400


@dataclass
class LinkData:
    source_id: uuid.UUID
    target_url: str
    target_id: uuid.UUID | None
    is_internal: bool
    nofollow: bool
    anchor_text: str | None


@dataclass
class CrawlFacts:
    robots_status: str | None
    sitemaps: list[dict[str, Any]]
    sitemap_url_count: int
    warnings: list[str]
    finished_at: datetime | None

    @property
    def page_limit_reached(self) -> bool:
        return any("page limit" in w for w in self.warnings)


class AnalysisContext:
    def __init__(
        self,
        *,
        config: CrawlConfig,
        settings: ProjectSettingsData,
        facts: CrawlFacts,
        pages: list[PageData],
        links: list[LinkData],
    ) -> None:
        self.config = config
        self.settings = settings
        self.thresholds = settings.analysis.thresholds
        self.facts = facts
        self.pages = pages
        self.links = links
        self.root_url = config.root_url
        self.by_url = {p.url: p for p in pages}
        self.by_id = {p.id: p for p in pages}
        self.outlinks: dict[uuid.UUID, list[LinkData]] = defaultdict(list)
        self.inlinks: dict[uuid.UUID, list[LinkData]] = defaultdict(list)
        for link in links:
            self.outlinks[link.source_id].append(link)
            if link.target_id is not None and link.target_id != link.source_id:
                self.inlinks[link.target_id].append(link)
        self.important_urls = self._resolve_important()

    # -- page sets ---------------------------------------------------------

    @property
    def analysable_pages(self) -> list[PageData]:
        return [p for p in self.pages if p.analysable]

    @property
    def indexable_pages(self) -> list[PageData]:
        return [p for p in self.pages if p.indexable]

    # -- configuration-driven context ---------------------------------------

    def _resolve_important(self) -> set[str]:
        urls = {self.root_url}
        for ref in self.settings.important_pages:
            url = normalise_url(ref, self.root_url)
            if url:
                urls.add(url)
        return urls

    def is_important(self, url: str) -> bool:
        return url in self.important_urls

    def priority_group(self, url: str) -> str | None:
        path = urlsplit(url).path or "/"
        for group in self.settings.page_groups:
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in group.patterns):
                return group.name
        return None

    def content_types_for(self, url: str) -> list[str]:
        path = urlsplit(url).path or "/"
        return [
            ct.key
            for ct in self.settings.content_types
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in ct.url_patterns)
        ]

    def linking_sources(self, page: PageData, limit: int = 10) -> list[str]:
        sources: list[str] = []
        for link in self.inlinks.get(page.id, []):
            source = self.by_id.get(link.source_id)
            if source and source.url not in sources:
                sources.append(source.url)
            if len(sources) >= limit:
                break
        return sources


def group_subject(*parts: str) -> str:
    """Short, stable identifier for a group of URLs or a shared value."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]
