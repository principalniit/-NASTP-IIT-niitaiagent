"""Deterministic comparison of two analysed crawls of the same project."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlPage
from app.modules.seo.models import SeoIssue, SeoScore

LIMIT = 50
CATEGORIES = ("overall", "technical", "on_page", "content", "internal_linking", "structured_data")


async def analysed_crawls(
    session: AsyncSession, project_id: uuid.UUID, organisation_id: uuid.UUID
) -> list[CrawlJob]:
    rows = await session.scalars(
        select(CrawlJob)
        .where(
            CrawlJob.project_id == project_id,
            CrawlJob.organisation_id == organisation_id,
            CrawlJob.analysis_status == AnalysisStatus.COMPLETED,
        )
        .order_by(CrawlJob.created_at.desc())
    )
    return list(rows)


async def _pages(session: AsyncSession, crawl: CrawlJob) -> dict[str, CrawlPage]:
    rows = await session.scalars(
        select(CrawlPage).where(
            CrawlPage.crawl_job_id == crawl.id, CrawlPage.organisation_id == crawl.organisation_id
        )
    )
    return {p.url: p for p in rows}


async def compare_crawls(
    session: AsyncSession,
    project_id: uuid.UUID,
    organisation_id: uuid.UUID,
    from_id: uuid.UUID | None = None,
    to_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    crawls = await analysed_crawls(session, project_id, organisation_id)
    by_id = {c.id: c for c in crawls}
    if (from_id and from_id not in by_id) or (to_id and to_id not in by_id):
        raise NotFoundError("Analysed crawl not found for this project")
    if from_id is None and to_id is None:
        if len(crawls) < 2:
            raise AppError(
                "At least two analysed crawls are needed for a comparison", code="not_enough_crawls"
            )
        new, old = crawls[0], crawls[1]
    else:
        new = by_id[to_id] if to_id else crawls[0]
        earlier: CrawlJob | None = (
            by_id[from_id]
            if from_id
            else next((c for c in crawls if c.created_at < new.created_at), None)
        )
        if earlier is None:
            raise AppError(
                "There is no earlier analysed crawl to compare with", code="not_enough_crawls"
            )
        old = earlier
    if old.created_at >= new.created_at:
        old, new = new, old

    scores = {
        s.crawl_job_id: s
        for s in await session.scalars(
            select(SeoScore).where(SeoScore.crawl_job_id.in_([old.id, new.id]))
        )
    }
    score_change: dict[str, Any] = {}
    for name in CATEGORIES:
        before = getattr(scores.get(old.id), name, None)
        after = getattr(scores.get(new.id), name, None)
        score_change[name] = {
            "from": before,
            "to": after,
            "change": round(after - before, 1)
            if before is not None and after is not None
            else None,
        }

    issues = list(
        await session.scalars(
            select(SeoIssue).where(
                SeoIssue.project_id == project_id, SeoIssue.organisation_id == organisation_id
            )
        )
    )

    def brief(i: SeoIssue) -> dict[str, Any]:
        return {
            "id": str(i.id),
            "rule_id": i.rule_id,
            "title": i.title,
            "severity": i.severity.value,
            "affected_url": i.affected_url,
            "affected_page_count": i.affected_page_count,
        }

    new_issues = [brief(i) for i in issues if i.first_crawl_id == new.id]
    resolved = [brief(i) for i in issues if i.resolved_in_crawl_id == new.id]
    recurring = [
        brief(i)
        for i in issues
        if i.last_crawl_id == new.id and i.recurrence_count > 0 and i.first_crawl_id != new.id
    ]

    before_pages, after_pages = await _pages(session, old), await _pages(session, new)
    added = sorted(set(after_pages) - set(before_pages))
    removed = sorted(set(before_pages) - set(after_pages))
    common = sorted(set(after_pages) & set(before_pages))
    status_changes: list[dict[str, Any]] = []
    title_changes: list[dict[str, Any]] = []
    description_changes: list[dict[str, Any]] = []
    redirect_changes: list[dict[str, Any]] = []
    content_changed: list[str] = []
    inlink_changes: list[dict[str, Any]] = []
    for url in common:
        a, b = before_pages[url], after_pages[url]
        if a.status_code != b.status_code:
            status_changes.append({"url": url, "from": a.status_code, "to": b.status_code})
        if (a.title or "") != (b.title or "") and b.analysable_hint():
            title_changes.append({"url": url, "from": a.title, "to": b.title})
        if (a.meta_description or "") != (b.meta_description or ""):
            description_changes.append(
                {"url": url, "from": a.meta_description, "to": b.meta_description}
            )
        if (a.final_url if a.redirect_chain else None) != (
            b.final_url if b.redirect_chain else None
        ):
            redirect_changes.append(
                {
                    "url": url,
                    "from": a.final_url if a.redirect_chain else None,
                    "to": b.final_url if b.redirect_chain else None,
                }
            )
        if a.content_hash and b.content_hash and a.content_hash != b.content_hash:
            content_changed.append(url)
        if a.inlinks_count != b.inlinks_count:
            inlink_changes.append({"url": url, "from": a.inlinks_count, "to": b.inlinks_count})

    def cap(items: list[Any]) -> dict[str, Any]:
        return {"count": len(items), "items": items[:LIMIT]}

    return {
        "from_crawl": {
            "id": str(old.id),
            "finished_at": old.finished_at,
            "pages": len(before_pages),
            "page_data_removed": old.pages_pruned_at is not None,
        },
        "to_crawl": {
            "id": str(new.id),
            "finished_at": new.finished_at,
            "pages": len(after_pages),
            "page_data_removed": new.pages_pruned_at is not None,
        },
        "score_change": score_change,
        "issues": {"new": cap(new_issues), "resolved": cap(resolved), "recurring": cap(recurring)},
        "pages": {
            "added": cap(added),
            "removed": cap(removed),
            "status_changes": cap(status_changes),
            "title_changes": cap(title_changes),
            "meta_description_changes": cap(description_changes),
            "redirect_changes": cap(redirect_changes),
            "content_changed": cap(content_changed),
            "inbound_link_changes": cap(inlink_changes),
        },
        "note": (
            "Issues are marked resolved only when the later crawl re-examined the affected pages."
        ),
    }
