"""Builders for in-memory analysis contexts used by rule tests."""

import random
import string
import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.models import FetchStatus
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.seo.context import AnalysisContext, CrawlFacts, LinkData, PageData

ROOT = "https://example.org/"


def _words(seed: str, count: int) -> list[str]:
    """Deterministic, page-specific vocabulary so generated pages never look alike."""
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    return [
        "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 9)))
        for _ in range(count)
    ]


ORG_LD = {"json_ld": [{"valid": True, "error": None, "types": ["EducationalOrganization"],
                       "data": {"@type": "EducationalOrganization", "name": "Example", "url": ROOT,
                                "logo": "x", "address": "x", "contactPoint": "x", "sameAs": "x"}}],
          "microdata": {"count": 0, "types": []}}  # fmt: skip


def page(path: str = "/", **overrides: Any) -> PageData:
    url = ROOT.rstrip("/") + path if path.startswith("/") else path
    data = PageData(
        id=uuid.uuid4(),
        url=url,
        fetch_status=FetchStatus.FETCHED,
        status_code=200,
        final_url=url,
        depth=0 if url == ROOT else 1,
        content_type="text/html",
        response_time_ms=120,
        title=" ".join(_words(path + "title", 5)).capitalize() + " overview",
        title_count=1,
        meta_description=f"A helpful meta description for the page at {path} that explains what it offers.",
        meta_description_count=1,
        canonical_url=url,
        canonical_count=1,
        lang="en",
        headings=[
            {"level": 1, "text": f"Heading {path}"},
            {"level": 2, "text": "Details"},
            {"level": 2, "text": "More"},
        ],
        h1_count=1,
        word_count=300,
        content_hash=uuid.uuid4().hex,
        text=" ".join(_words(path + "text", 300)),
        structured_data=ORG_LD
        if url == ROOT
        else {"json_ld": [], "microdata": {"count": 0, "types": []}},
        internal_links_count=3,
        inlinks_count=3,
        in_sitemap=True,
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


def link(source: PageData, target: PageData | str, **kw: Any) -> LinkData:
    if isinstance(target, str):
        return LinkData(
            source.id, target, None, kw.get("is_internal", False), kw.get("nofollow", False), "x"
        )
    return LinkData(
        source.id,
        target.url,
        target.id,
        kw.get("is_internal", True),
        kw.get("nofollow", False),
        kw.get("anchor", "link"),
    )


def context(
    pages: list[PageData],
    links: list[LinkData] | None = None,
    settings: dict[str, Any] | None = None,
    root: str = ROOT,
    **facts: Any,
) -> AnalysisContext:
    base_facts: dict[str, Any] = {
        "robots_status": "found",
        "sitemaps": [{"url": root + "sitemap.xml", "status": "ok", "url_count": len(pages)}],
        "sitemap_url_count": len(pages),
        "warnings": [],
        "finished_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    base_facts.update(facts)
    if links is None:
        links = []
        home = next((p for p in pages if p.url == root), None)
        if home is not None:
            links = [link(home, p) for p in pages if p is not home]
            links += [link(p, home) for p in pages if p is not home]
    return AnalysisContext(
        config=CrawlConfig(
            root_url=root,
            allowed_hosts=["example.org"],
            max_pages=100,
            max_depth=5,
            concurrency=1,
            timeout_seconds=5,
            delay_ms=0,
            user_agent="t",
        ),
        settings=ProjectSettingsData.model_validate(settings or {}),
        facts=CrawlFacts(**base_facts),
        pages=pages,
        links=links,
    )
