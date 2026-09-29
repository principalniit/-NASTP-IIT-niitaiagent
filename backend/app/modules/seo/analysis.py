"""Run the deterministic SEO engine over one completed crawl and persist the results.

Everything happens in one transaction: rules, scores, structured-data findings,
internal-link suggestions and the issue lifecycle. No AI provider is involved.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import undefer

from app.core.database import get_session_factory
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlLink, CrawlPage, CrawlStatus
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.projects.service import get_settings_row
from app.modules.seo.context import AnalysisContext, CrawlFacts, LinkData, PageData
from app.modules.seo.findings import MAX_STORED_URLS, Finding
from app.modules.seo.link_opportunities import suggest_links
from app.modules.seo.models import (
    InternalLinkRecommendation,
    ResolutionStatus,
    SchemaFinding,
    SeoIssue,
    SeoScore,
)
from app.modules.seo.priority import prioritise
from app.modules.seo.rules import ALL_RULES
from app.modules.seo.schema_check import check_page
from app.modules.seo.scoring import compute_score

logger = logging.getLogger(__name__)

PAGE_FIELDS = [f for f in PageData.__dataclass_fields__ if f not in ("id", "text")]


class AnalysisError(Exception):
    """A user-facing reason why a crawl cannot be analysed."""


def _page_data(row: CrawlPage) -> PageData:
    data = PageData(id=row.id, url=row.url, fetch_status=row.fetch_status, text=row.text_content)
    for name in PAGE_FIELDS:
        if hasattr(row, name):
            setattr(data, name, getattr(row, name))
    return data


async def load_context(session: AsyncSession, job: CrawlJob) -> AnalysisContext:
    project = await session.get(Project, job.project_id)
    if project is None:
        raise AnalysisError("The project for this crawl no longer exists")
    settings = ProjectSettingsData.model_validate(
        (await get_settings_row(session, project)).settings
    )
    pages = [
        _page_data(row)
        for row in await session.scalars(
            select(CrawlPage)
            .options(undefer(CrawlPage.text_content))
            .where(
                CrawlPage.crawl_job_id == job.id, CrawlPage.organisation_id == job.organisation_id
            )
        )
    ]
    links = [
        LinkData(
            link.source_page_id,
            link.target_url,
            link.target_page_id,
            link.is_internal,
            link.nofollow,
            link.anchor_text,
        )
        for link in await session.scalars(
            select(CrawlLink).where(
                CrawlLink.crawl_job_id == job.id, CrawlLink.organisation_id == job.organisation_id
            )
        )
    ]
    facts = CrawlFacts(
        robots_status=job.robots_status,
        sitemaps=job.sitemaps,
        sitemap_url_count=job.sitemap_url_count,
        warnings=job.warnings,
        finished_at=job.finished_at,
    )
    return AnalysisContext(
        config=CrawlConfig.model_validate(job.config),
        settings=settings,
        facts=facts,
        pages=pages,
        links=links,
    )


def run_rules(ctx: AnalysisContext) -> list[Finding]:
    findings: dict[str, Finding] = {}
    for rule in ALL_RULES:
        for finding in rule.evaluate(ctx):
            findings.setdefault(finding.issue_key, finding)
    return list(findings.values())


def _verified_resolved(issue: SeoIssue, crawled: set[str]) -> bool:
    """An issue is resolved only if this crawl re-examined what it concerned."""
    if issue.scope == "site":
        return True
    if issue.scope == "page":
        return issue.affected_url in crawled
    return bool(issue.affected_urls) and all(url in crawled for url in issue.affected_urls)


async def analyse_crawl(
    crawl_id: uuid.UUID, *, factory: async_sessionmaker[AsyncSession] | None = None
) -> None:
    factory = factory or get_session_factory()
    async with factory() as session:
        job = await session.get(CrawlJob, crawl_id, with_for_update=True)
        if job is None:
            raise AnalysisError("Crawl not found")
        if job.status != CrawlStatus.COMPLETED:
            raise AnalysisError("Only completed crawls can be analysed")
        newer = await session.scalar(
            select(CrawlJob.id).where(
                CrawlJob.project_id == job.project_id,
                CrawlJob.created_at > job.created_at,
                CrawlJob.analysis_status == AnalysisStatus.COMPLETED,
            )
        )
        if newer is not None:
            raise AnalysisError("A newer crawl of this project has already been analysed")

        ctx = await load_context(session, job)
        findings = run_rules(ctx)
        score = compute_score(ctx, findings)
        suggestions = suggest_links(ctx)
        detected_at = job.finished_at or datetime.now(UTC)

        for model in (SchemaFinding, InternalLinkRecommendation, SeoScore):
            await session.execute(delete(model).where(model.crawl_job_id == job.id))

        for page in ctx.analysable_pages:
            for check in check_page(page.structured_data):
                session.add(
                    SchemaFinding(
                        organisation_id=job.organisation_id,
                        crawl_job_id=job.id,
                        page_id=page.id,
                        format=check.format,
                        schema_types=check.types,
                        is_valid=check.valid,
                        errors=check.errors[:50],
                        warnings=check.warnings[:50],
                    )
                )
        for s in suggestions:
            session.add(
                InternalLinkRecommendation(
                    organisation_id=job.organisation_id,
                    crawl_job_id=job.id,
                    source_page_id=s.source.id,
                    target_page_id=s.target.id,
                    anchor_text=s.anchor_text[:300],
                    reason=s.reason,
                    evidence={
                        "snippet": s.snippet,
                        "target_url": s.target.url,
                        "source_url": s.source.url,
                        "target_inlinks": s.target.inlinks_count,
                    },
                    relevance=s.relevance,
                )
            )
        session.add(
            SeoScore(
                organisation_id=job.organisation_id,
                project_id=job.project_id,
                crawl_job_id=job.id,
                overall=score.overall,
                pages_analysed=score.pages_analysed,
                breakdown=score.breakdown,
                created_at=detected_at,
                **score.categories,
            )
        )

        existing = {
            issue.issue_key: issue
            for issue in await session.scalars(
                select(SeoIssue).where(
                    SeoIssue.project_id == job.project_id,
                    SeoIssue.organisation_id == job.organisation_id,
                )
            )
        }
        seen: set[str] = set()
        for finding in findings:
            key = finding.issue_key
            seen.add(key)
            priority, factors = prioritise(ctx, finding)
            values = {
                "rule_id": finding.rule_id,
                "scope": finding.scope,
                "category": finding.category,
                "severity": finding.severity,
                "title": finding.title,
                "description": finding.description,
                "recommendation": finding.recommendation,
                "evidence": finding.evidence,
                "affected_url": finding.primary_url,
                "affected_urls": finding.affected_urls[:MAX_STORED_URLS],
                "affected_page_count": finding.affected_page_count,
                "confidence": finding.confidence,
                "effort": finding.effort,
                "priority_score": priority,
                "priority_breakdown": factors,
                "auto_fix_eligible": finding.auto_fix_eligible,
                "last_detected_at": detected_at,
                "last_crawl_id": job.id,
            }
            issue = existing.get(key)
            if issue is None:
                session.add(
                    SeoIssue(
                        organisation_id=job.organisation_id,
                        project_id=job.project_id,
                        issue_key=key,
                        first_detected_at=detected_at,
                        first_crawl_id=job.id,
                        resolution_status=ResolutionStatus.OPEN,
                        **values,
                    )
                )
                continue
            for name, value in values.items():
                setattr(issue, name, value)
            if issue.resolution_status == ResolutionStatus.RESOLVED:
                issue.resolution_status = ResolutionStatus.OPEN
                issue.recurrence_count += 1
                issue.resolved_at = None
                issue.resolved_in_crawl_id = None

        crawled = set(ctx.by_url)
        for key, issue in existing.items():
            if key in seen or issue.resolution_status == ResolutionStatus.RESOLVED:
                continue
            if _verified_resolved(issue, crawled):
                issue.resolution_status = ResolutionStatus.RESOLVED
                issue.resolved_at = detected_at
                issue.resolved_in_crawl_id = job.id

        job.analysis_status = AnalysisStatus.COMPLETED
        job.analysed_at = datetime.now(UTC)
        job.analysis_error = None
        await session.commit()
        logger.info(
            "Analysis completed",
            extra={"crawl_job_id": str(job.id), "findings": len(findings), "score": score.overall},
        )
