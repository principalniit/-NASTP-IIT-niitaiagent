import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crawler.models import AnalysisStatus, CrawlStatus, FetchStatus


class CrawlStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incremental: bool = Field(
        default=False,
        description="Send conditional requests and reuse unchanged pages from the last crawl.",
    )


class CrawlJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    status: CrawlStatus
    incremental: bool
    previous_crawl_id: uuid.UUID | None
    config: dict[str, Any]
    pages_discovered: int
    pages_crawled: int
    pages_failed: int
    pages_blocked: int
    robots_status: str | None
    sitemaps: list[dict[str, Any]]
    sitemap_url_count: int
    warnings: list[str]
    error_message: str | None
    analysis_status: AnalysisStatus
    analysed_at: datetime | None
    analysis_error: str | None
    requested_by_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CrawlPageRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    final_url: str | None
    status_code: int | None
    fetch_status: FetchStatus
    depth: int | None
    discovered_via: str
    content_type: str | None
    title: str | None
    word_count: int | None
    response_time_ms: int | None
    h1_count: int
    images_missing_alt: int
    internal_links_count: int
    inlinks_count: int
    is_noindex: bool
    in_sitemap: bool
    is_orphan: bool


class LinkOut(BaseModel):
    url: str
    anchor_text: str | None
    nofollow: bool
    is_internal: bool
    page_id: uuid.UUID | None = None
    status_code: int | None = None


class CrawlPageDetail(CrawlPageRow):
    error: str | None
    content_length: int | None
    redirect_chain: list[dict[str, Any]]
    title_count: int
    meta_description: str | None
    meta_description_count: int
    meta_robots: str | None
    x_robots_tag: str | None
    is_nofollow: bool
    canonical_url: str | None
    canonical_count: int
    lang: str | None
    headings: list[dict[str, Any]]
    content_hash: str | None
    images: list[dict[str, Any]]
    image_count: int
    structured_data: dict[str, Any]
    hreflang: list[dict[str, Any]]
    external_links_count: int
    fetched_at: datetime | None
    outlinks: list[LinkOut] = Field(default_factory=list)
    inlinks: list[LinkOut] = Field(default_factory=list)


class BrokenLinkOut(BaseModel):
    source_page_id: uuid.UUID
    source_url: str
    target_page_id: uuid.UUID
    target_url: str
    anchor_text: str | None
    status_code: int | None
    fetch_status: FetchStatus


class DuplicateGroup(BaseModel):
    content_hash: str
    urls: list[str]


class CrawlSummary(BaseModel):
    pages_total: int
    status_classes: dict[str, int]
    fetch_statuses: dict[str, int]
    average_response_time_ms: int | None
    slowest_response_time_ms: int | None
    noindex_pages: int
    pages_in_sitemap: int
    orphan_pages: int
    broken_internal_links: int
    redirects: int
    duplicate_content_groups: list[DuplicateGroup]


StatusClass = Literal["2xx", "3xx", "4xx", "5xx", "none"]
PageSort = Literal["url", "status_code", "response_time_ms", "word_count", "depth", "inlinks_count"]
