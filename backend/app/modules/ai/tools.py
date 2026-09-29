"""Typed, read-only tools the AI may use. Each is scoped to one authorised project.

The model never runs SQL, shell commands or network requests. It can only ask for one of
these tools by name, with arguments validated against the tool's model.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, undefer

from app.core.errors import AppError
from app.modules.crawler.models import CrawlJob, CrawlLink, CrawlPage
from app.modules.crawler.urls import normalise_url
from app.modules.projects.models import Project
from app.modules.seo.compare import compare_crawls
from app.modules.seo.models import (
    Category,
    InternalLinkRecommendation,
    ResolutionStatus,
    SchemaFinding,
    SeoIssue,
    SeoScore,
    Severity,
)
from app.modules.seo.rules import ALL_RULES
from app.modules.seo.service import latest_analysed_crawl, summary

EXCERPT_CHARS = 1500


class ToolError(Exception):
    """The tool could not answer; the message is returned to the model."""


@dataclass
class ToolContext:
    session: AsyncSession
    project: Project

    @property
    def org_id(self) -> uuid.UUID:
        return self.project.organisation_id

    async def latest_crawl(self) -> CrawlJob:
        crawl = await latest_analysed_crawl(self.session, self.project.id, self.org_id)
        if crawl is None:
            raise ToolError("This project has no analysed crawl yet.")
        return crawl


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssuesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Severity | None = None
    category: Category | None = None
    limit: int = Field(default=10, ge=1, le=20)


class IssueArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: uuid.UUID


class PageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(
        min_length=1, max_length=2048, description="Page URL or path, e.g. /admissions"
    )


class OptionalPageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str | None = Field(default=None, max_length=2048)


def issue_brief(issue: SeoIssue, with_evidence: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(issue.id),
        "rule_id": issue.rule_id,
        "title": issue.title,
        "severity": issue.severity.value,
        "category": issue.category.value,
        "status": issue.resolution_status.value,
        "affected_url": issue.affected_url,
        "affected_page_count": issue.affected_page_count,
        "priority": issue.priority_score,
        "recommendation": issue.recommendation,
    }
    if with_evidence:
        data["description"] = issue.description
        data["evidence"] = issue.evidence
        data["affected_urls"] = issue.affected_urls[:20]
        data["first_detected_at"] = issue.first_detected_at.isoformat()
        data["recurrence_count"] = issue.recurrence_count
    return data


async def get_project_summary(ctx: ToolContext, _: NoArgs) -> dict[str, Any]:
    crawl = await latest_analysed_crawl(ctx.session, ctx.project.id, ctx.org_id)
    result: dict[str, Any] = {
        "project": {"name": ctx.project.name, "root_url": ctx.project.root_url},
        "latest_analysed_crawl": None,
    }
    if crawl is None:
        return result
    score = await ctx.session.scalar(select(SeoScore).where(SeoScore.crawl_job_id == crawl.id))
    counts = await summary(ctx.session, ctx.project.id, ctx.org_id)
    result["latest_analysed_crawl"] = {
        "id": str(crawl.id),
        "finished_at": crawl.finished_at.isoformat() if crawl.finished_at else None,
        "pages_recorded": crawl.pages_discovered,
        "warnings": crawl.warnings,
    }
    if score is not None:
        result["scores"] = {
            "overall": score.overall,
            "technical": score.technical,
            "on_page": score.on_page,
            "content": score.content,
            "internal_linking": score.internal_linking,
            "structured_data": score.structured_data,
            "pages_analysed": score.pages_analysed,
            "note": "Site-health indicator from this platform's rules, not a search ranking.",
        }
    result["open_issues"] = {
        "total": counts.open_total,
        "by_severity": counts.open_by_severity,
        "by_category": counts.open_by_category,
        "new_in_latest_crawl": counts.new_in_latest,
        "resolved_in_latest_crawl": counts.resolved_in_latest,
    }
    return result


async def get_crawl_status(ctx: ToolContext, _: NoArgs) -> dict[str, Any]:
    crawl = await ctx.session.scalar(
        select(CrawlJob)
        .where(CrawlJob.project_id == ctx.project.id, CrawlJob.organisation_id == ctx.org_id)
        .order_by(CrawlJob.created_at.desc())
        .limit(1)
    )
    if crawl is None:
        return {"latest_crawl": None}
    return {
        "latest_crawl": {
            "id": str(crawl.id),
            "status": crawl.status.value,
            "analysis_status": crawl.analysis_status.value,
            "pages_discovered": crawl.pages_discovered,
            "pages_crawled": crawl.pages_crawled,
            "pages_failed": crawl.pages_failed,
            "pages_blocked": crawl.pages_blocked,
            "robots_status": crawl.robots_status,
            "sitemap_urls": crawl.sitemap_url_count,
            "warnings": crawl.warnings,
        }
    }


async def get_seo_issues(ctx: ToolContext, args: IssuesArgs) -> dict[str, Any]:
    query = select(SeoIssue).where(
        SeoIssue.project_id == ctx.project.id,
        SeoIssue.organisation_id == ctx.org_id,
        SeoIssue.resolution_status == ResolutionStatus.OPEN,
    )
    if args.severity:
        query = query.where(SeoIssue.severity == args.severity)
    if args.category:
        query = query.where(SeoIssue.category == args.category)
    total = await ctx.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await ctx.session.scalars(
        query.order_by(SeoIssue.priority_score.desc()).limit(args.limit)
    )
    return {"total_matching": total, "issues": [issue_brief(i) for i in rows]}


async def get_issue_evidence(ctx: ToolContext, args: IssueArgs) -> dict[str, Any]:
    issue = await ctx.session.scalar(
        select(SeoIssue).where(
            SeoIssue.id == args.issue_id,
            SeoIssue.project_id == ctx.project.id,
            SeoIssue.organisation_id == ctx.org_id,
        )
    )
    if issue is None:
        raise ToolError("No issue with that id exists in this project.")
    return issue_brief(issue, with_evidence=True)


async def _page(ctx: ToolContext, crawl: CrawlJob, url: str) -> CrawlPage:
    target = normalise_url(url, ctx.project.root_url)
    page = await ctx.session.scalar(
        select(CrawlPage)
        .options(undefer(CrawlPage.text_content))
        .where(
            CrawlPage.crawl_job_id == crawl.id,
            CrawlPage.organisation_id == ctx.org_id,
            CrawlPage.url == target,
        )
    )
    if page is None:
        raise ToolError(f"The page {url} was not found in the latest analysed crawl.")
    return page


def page_facts(page: CrawlPage) -> dict[str, Any]:
    return {
        "url": page.url,
        "status_code": page.status_code,
        "title": page.title,
        "meta_description": page.meta_description,
        "h1": [h["text"] for h in page.headings if h.get("level") == 1],
        "headings": [f"H{h['level']}: {h['text']}" for h in page.headings[:25]],
        "word_count": page.word_count,
        "lang": page.lang,
        "is_noindex": page.is_noindex,
        "canonical_url": page.canonical_url,
        "inbound_internal_links": page.inlinks_count,
        "text_excerpt": (page.text_content or "")[:EXCERPT_CHARS],
    }


async def page_issues(ctx: ToolContext, url: str) -> list[SeoIssue]:
    rows = await ctx.session.scalars(
        select(SeoIssue)
        .where(
            SeoIssue.project_id == ctx.project.id,
            SeoIssue.organisation_id == ctx.org_id,
            SeoIssue.resolution_status == ResolutionStatus.OPEN,
            SeoIssue.affected_urls.contains([url]),
        )
        .order_by(SeoIssue.priority_score.desc())
    )
    return list(rows)


async def get_page_details(ctx: ToolContext, args: PageArgs) -> dict[str, Any]:
    crawl = await ctx.latest_crawl()
    page = await _page(ctx, crawl, args.url)
    facts = page_facts(page)
    facts["open_issues"] = [issue_brief(i) for i in await page_issues(ctx, page.url)]
    return facts


async def get_internal_links(ctx: ToolContext, args: PageArgs) -> dict[str, Any]:
    crawl = await ctx.latest_crawl()
    page = await _page(ctx, crawl, args.url)
    source = aliased(CrawlPage)
    inbound = await ctx.session.execute(
        select(source.url, CrawlLink.anchor_text)
        .join(source, source.id == CrawlLink.source_page_id)
        .where(CrawlLink.target_page_id == page.id, CrawlLink.crawl_job_id == crawl.id)
        .limit(30)
    )
    outbound = await ctx.session.scalars(
        select(CrawlLink)
        .where(CrawlLink.source_page_id == page.id, CrawlLink.crawl_job_id == crawl.id)
        .limit(30)
    )
    suggestions = await ctx.session.scalars(
        select(InternalLinkRecommendation).where(
            InternalLinkRecommendation.crawl_job_id == crawl.id,
            InternalLinkRecommendation.target_page_id == page.id,
        )
    )
    return {
        "url": page.url,
        "inbound": [{"from": u, "anchor_text": a} for u, a in inbound.all()],
        "outbound": [
            {"to": link.target_url, "anchor_text": link.anchor_text, "internal": link.is_internal}
            for link in outbound
        ],
        "suggested_links_to_this_page": [
            {"from": s.evidence.get("source_url"), "anchor_text": s.anchor_text}
            for s in suggestions
        ],
    }


async def get_schema_findings(ctx: ToolContext, args: OptionalPageArgs) -> dict[str, Any]:
    crawl = await ctx.latest_crawl()
    query = (
        select(SchemaFinding, CrawlPage.url)
        .join(CrawlPage, CrawlPage.id == SchemaFinding.page_id)
        .where(SchemaFinding.crawl_job_id == crawl.id, SchemaFinding.organisation_id == ctx.org_id)
    )
    if args.url:
        page = await _page(ctx, crawl, args.url)
        query = query.where(SchemaFinding.page_id == page.id)
    rows = await ctx.session.execute(query.limit(30))
    return {
        "findings": [
            {
                "url": url,
                "types": f.schema_types,
                "valid": f.is_valid,
                "errors": f.errors[:5],
                "suggestions": f.warnings[:5],
            }
            for f, url in rows.all()
        ]
    }


async def compare_latest_crawls(ctx: ToolContext, _: NoArgs) -> dict[str, Any]:
    try:
        return await compare_crawls(ctx.session, ctx.project.id, ctx.org_id)
    except AppError as exc:
        raise ToolError(exc.message) from exc


async def get_rule(ctx: ToolContext, args: "RuleArgs") -> dict[str, Any]:
    for rule in ALL_RULES:
        if rule.id == args.rule_id:
            return rule.catalogue_entry()
    raise ToolError("Unknown rule id.")


class RuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str = Field(max_length=80)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "get_project_summary",
            "Scores, open issue counts and latest crawl facts.",
            NoArgs,
            get_project_summary,
        ),
        Tool(
            "get_crawl_status",
            "Status and counts of the most recent crawl.",
            NoArgs,
            get_crawl_status,
        ),
        Tool(
            "get_seo_issues",
            "Open issues by priority, optionally filtered by severity or category.",
            IssuesArgs,
            get_seo_issues,
        ),
        Tool(
            "get_issue_evidence",
            "Full evidence and recommendation for one issue.",
            IssueArgs,
            get_issue_evidence,
        ),
        Tool(
            "get_page_details",
            "Metadata, headings, text excerpt and open issues for one page.",
            PageArgs,
            get_page_details,
        ),
        Tool(
            "get_internal_links",
            "Inbound and outbound links and link suggestions for one page.",
            PageArgs,
            get_internal_links,
        ),
        Tool(
            "get_schema_findings",
            "Structured data found, optionally for one page.",
            OptionalPageArgs,
            get_schema_findings,
        ),
        Tool(
            "compare_crawls",
            "What changed between the two most recent analysed crawls.",
            NoArgs,
            compare_latest_crawls,
        ),
        Tool("get_rule", "What a rule checks and its standard recommendation.", RuleArgs, get_rule),
    ]
}


async def run_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool '{name}'. Available tools: {', '.join(TOOLS)}.")
    try:
        args = tool.args.model_validate(arguments)
    except ValueError as exc:
        raise ToolError(f"Invalid arguments for {name}: {exc}") from exc
    return await tool.run(ctx, args)
