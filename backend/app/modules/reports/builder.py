"""Collects the facts a management report is rendered from.

Everything comes from stored crawl, analysis and approval records; nothing is estimated.
The executive summary and action plan are written by fixed rules, so a complete report
is produced with AI switched off. AI output appears only in its own, labelled section.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.ai.models import (
    AIAnalysis,
    AIKind,
    AIStatus,
    RecommendationStatus,
    SeoRecommendation,
)
from app.modules.crawler.models import CrawlJob, CrawlPage
from app.modules.crawler.service import summary as crawl_summary
from app.modules.organisations.models import Organisation
from app.modules.projects.models import Project
from app.modules.reports.models import Report
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

SECTION_LIMIT = 10
PRIORITY_LIMIT = 25
LISTED_URLS = 10
EVIDENCE_TEXT = 300

CATEGORY_LABELS = {
    Category.TECHNICAL: "Technical SEO",
    Category.ON_PAGE: "On-page SEO",
    Category.CONTENT: "Content quality",
    Category.INTERNAL_LINKING: "Internal linking",
    Category.STRUCTURED_DATA: "Structured data",
}
SEVERITY_ORDER = [s.value for s in Severity]

LIMITATIONS = [
    "The site-health score measures technical and on-page quality found in this crawl. "
    "It is not a search engine ranking and does not predict rankings or traffic.",
    "This platform holds no search ranking, traffic, keyword volume, backlink or "
    "competitor data, so none is reported.",
    "Pages are analysed as the server delivered them. Content added by JavaScript in the "
    "browser was not rendered.",
    "Only pages within the crawl limits were analysed; pages beyond them are not covered.",
    "Links to other websites were recorded but not checked.",
    "Response times are single measurements from the server running this platform, not "
    "visitor experience data such as Core Web Vitals.",
    "Issue statuses are as recorded when this report was generated. An issue is only marked "
    "resolved after a later crawl confirms it.",
]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _text(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(_text(v) for v in value[:LISTED_URLS])
        return text + (
            f" (and {len(value) - LISTED_URLS} more)" if len(value) > LISTED_URLS else ""
        )
    if isinstance(value, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {_text(v)}" for k, v in list(value.items())[:8])
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    return text if len(text) <= EVIDENCE_TEXT else text[: EVIDENCE_TEXT - 1] + "…"


_ACRONYMS = {
    "url": "URL",
    "urls": "URLs",
    "http": "HTTP",
    "https": "HTTPS",
    "h1": "H1",
    "id": "ID",
    "ms": "ms",
}


def _label(key: str) -> str:
    raw = key.lower().split("_")
    words = [_ACRONYMS.get(w, w) for w in raw]
    first = words[0] if raw[0] in _ACRONYMS else words[0].capitalize()
    return " ".join([first, *words[1:]])


def issue_facts(issue: SeoIssue) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "rule_id": issue.rule_id,
        "title": issue.title,
        "severity": issue.severity.value,
        "category": issue.category.value,
        "priority": round(issue.priority_score),
        "scope": issue.scope,
        "effort": issue.effort,
        "affected_count": issue.affected_page_count,
        "affected_urls": issue.affected_urls[:LISTED_URLS],
        "description": issue.description,
        "recommendation": issue.recommendation,
        "evidence": [
            {"label": _label(key), "value": _text(value)}
            for key, value in list(issue.evidence.items())[:8]
        ],
        "first_detected_at": _iso(issue.first_detected_at),
        "recurrence_count": issue.recurrence_count,
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def executive_summary(data: dict[str, Any]) -> list[str]:
    meta, health, counts = data["meta"], data["health"], data["counts"]
    sev = counts["by_severity"]
    lines = [
        f"This report covers the crawl of {meta['site']} that finished on "
        f"{meta['crawl_finished_label']}. It analysed {_plural(meta['pages_analysed'], 'page')}."
    ]
    if health["overall"] is not None:
        line = f"The overall site-health score is {health['overall']:.0f} out of 100"
        if health["change"] is not None and round(health["change"]) != 0:
            direction = "up" if health["change"] > 0 else "down"
            line += f", {direction} {abs(health['change']):.0f} points since the previous crawl"
        lines.append(line + ".")
    else:
        lines.append("There was not enough analysable content to calculate an overall score.")
    if counts["open_total"]:
        lines.append(
            f"There are {_plural(counts['open_total'], 'open issue')}: {sev['critical']} critical, "
            f"{sev['high']} high, {sev['medium']} medium and {sev['low']} low severity."
        )
    else:
        lines.append("No open issues were found.")
    if sev["critical"] or sev["high"]:
        lines.append(
            "Critical and high-severity issues are listed in sections 4 and 5 and lead the "
            "action plan in section 12."
        )
    changes = data["changes"]
    if changes:
        lines.append(
            f"Since the previous crawl, {_plural(changes['new'], 'issue')} "
            f"{'was' if changes['new'] == 1 else 'were'} newly detected and "
            f"{changes['resolved']} {'was' if changes['resolved'] == 1 else 'were'} "
            "confirmed resolved."
        )
    return lines


def action_plan(open_issues: list[SeoIssue]) -> dict[str, list[dict[str, Any]]]:
    ranked = sorted(open_issues, key=lambda i: i.priority_score, reverse=True)
    fix_first = [i for i in ranked if i.severity in (Severity.CRITICAL, Severity.HIGH)][
        :SECTION_LIMIT
    ]
    used = {i.id for i in fix_first}
    quick = [
        i
        for i in ranked
        if i.id not in used and i.effort == "low" and i.severity != Severity.INFORMATIONAL
    ][:SECTION_LIMIT]
    used |= {i.id for i in quick}
    later = [i for i in ranked if i.id not in used and i.severity != Severity.INFORMATIONAL][
        :SECTION_LIMIT
    ]

    def item(i: SeoIssue) -> dict[str, Any]:
        return {
            "id": str(i.id),
            "title": i.title,
            "severity": i.severity.value,
            "effort": i.effort,
            "affected_count": i.affected_page_count,
            "recommendation": i.recommendation,
        }

    return {
        "fix_first": [item(i) for i in fix_first],
        "quick_wins": [item(i) for i in quick],
        "plan_next": [item(i) for i in later],
    }


async def _ai_section(session: AsyncSession, report: Report, crawl: CrawlJob) -> dict[str, Any]:
    if not report.include_ai:
        return {"included": False, "summary": None, "recommendations": []}
    analysis = await session.scalar(
        select(AIAnalysis)
        .where(
            AIAnalysis.project_id == report.project_id,
            AIAnalysis.organisation_id == report.organisation_id,
            AIAnalysis.crawl_job_id == crawl.id,
            AIAnalysis.kind == AIKind.MANAGEMENT_SUMMARY,
            AIAnalysis.status == AIStatus.COMPLETED,
        )
        .order_by(AIAnalysis.finished_at.desc())
        .limit(1)
    )
    recs = await session.scalars(
        select(SeoRecommendation)
        .where(
            SeoRecommendation.project_id == report.project_id,
            SeoRecommendation.organisation_id == report.organisation_id,
            SeoRecommendation.status == RecommendationStatus.ACCEPTED,
        )
        .order_by(SeoRecommendation.created_at.desc())
        .limit(SECTION_LIMIT)
    )
    return {
        "included": True,
        "summary": (
            {
                "output": analysis.output,
                "model": analysis.model,
                "generated_at": _iso(analysis.finished_at),
            }
            if analysis and analysis.output
            else None
        ),
        "recommendations": [
            {"title": r.title, "body": r.body, "steps": r.steps, "page_url": r.page_url}
            for r in recs
        ],
    }


async def build(session: AsyncSession, report: Report) -> dict[str, Any]:
    project = await session.get(Project, report.project_id)
    org = await session.get(Organisation, report.organisation_id)
    crawl = await session.get(CrawlJob, report.crawl_job_id) if report.crawl_job_id else None
    if project is None or org is None or project.deleted_at is not None:
        raise AppError("The project no longer exists.")
    if crawl is None or crawl.organisation_id != org.id or crawl.project_id != project.id:
        raise AppError("The crawl this report was requested for no longer exists.")

    score = await session.scalar(select(SeoScore).where(SeoScore.crawl_job_id == crawl.id))
    previous = await session.scalar(
        select(SeoScore)
        .where(
            SeoScore.project_id == project.id,
            SeoScore.organisation_id == org.id,
            SeoScore.created_at < (score.created_at if score else crawl.created_at),
        )
        .order_by(SeoScore.created_at.desc())
        .limit(1)
    )
    breakdown = score.breakdown if score else {}
    categories = [
        {
            "key": c.value,
            "label": CATEGORY_LABELS[c],
            "score": getattr(score, c.value) if score else None,
            "weight": breakdown.get("categories", {}).get(c.value, {}).get("weight"),
            "note": breakdown.get("categories", {}).get(c.value, {}).get("note"),
        }
        for c in Category
    ]
    overall = score.overall if score else None
    change = (
        round(overall - previous.overall, 1)
        if overall is not None and previous is not None and previous.overall is not None
        else None
    )

    issues = list(
        await session.scalars(
            select(SeoIssue)
            .where(SeoIssue.project_id == project.id, SeoIssue.organisation_id == org.id)
            .order_by(SeoIssue.priority_score.desc())
        )
    )
    open_issues = [i for i in issues if i.resolution_status == ResolutionStatus.OPEN]
    by_severity = {s: sum(1 for i in open_issues if i.severity.value == s) for s in SEVERITY_ORDER}

    by_category: dict[str, Any] = {}
    for c in Category:
        rows = [i for i in open_issues if i.category == c]
        by_category[c.value] = {
            "label": CATEGORY_LABELS[c],
            "score": getattr(score, c.value) if score else None,
            "open": len(rows),
            "by_severity": {
                s: sum(1 for i in rows if i.severity.value == s) for s in SEVERITY_ORDER
            },
            "issues": [issue_facts(i) for i in rows[:SECTION_LIMIT]],
        }

    crawl_facts = (await crawl_summary(session, crawl)).model_dump(mode="json")
    config = crawl.config or {}

    link_total = (
        await session.scalar(
            select(func.count()).where(InternalLinkRecommendation.crawl_job_id == crawl.id)
        )
        or 0
    )
    source, target = CrawlPage.__table__.alias("s"), CrawlPage.__table__.alias("t")
    link_rows = await session.execute(
        select(
            source.c.url,
            target.c.url,
            InternalLinkRecommendation.anchor_text,
            InternalLinkRecommendation.reason,
        )
        .join(source, source.c.id == InternalLinkRecommendation.source_page_id)
        .join(target, target.c.id == InternalLinkRecommendation.target_page_id)
        .where(
            InternalLinkRecommendation.crawl_job_id == crawl.id,
            InternalLinkRecommendation.organisation_id == org.id,
        )
        .order_by(InternalLinkRecommendation.relevance.desc())
        .limit(SECTION_LIMIT)
    )

    findings = list(
        await session.execute(
            select(SchemaFinding, CrawlPage.url)
            .join(CrawlPage, CrawlPage.id == SchemaFinding.page_id)
            .where(SchemaFinding.crawl_job_id == crawl.id, SchemaFinding.organisation_id == org.id)
        )
    )
    types: dict[str, int] = {}
    for finding, _ in findings:
        for t in finding.schema_types:
            types[t] = types.get(t, 0) + 1
    invalid = [(f, url) for f, url in findings if not f.is_valid]

    try:
        comparison = await compare_crawls(session, project.id, org.id, to_id=crawl.id)
        changes: dict[str, Any] | None = {
            "from_finished_at": _iso(comparison["from_crawl"]["finished_at"]),
            "new": comparison["issues"]["new"]["count"],
            "resolved": comparison["issues"]["resolved"]["count"],
            "recurring": comparison["issues"]["recurring"]["count"],
            "pages_added": comparison["pages"]["added"]["count"],
            "pages_removed": comparison["pages"]["removed"]["count"],
            "status_changes": comparison["pages"]["status_changes"]["count"],
            "title_changes": comparison["pages"]["title_changes"]["count"],
            "content_changed": comparison["pages"]["content_changed"]["count"],
        }
    except AppError:
        changes = None

    data: dict[str, Any] = {
        "meta": {
            "title": report.title,
            "organisation": org.name,
            "project": project.name,
            "site": project.root_url,
            "timezone": org.timezone,
            "crawl_id": str(crawl.id),
            "crawl_started_at": _iso(crawl.started_at),
            "crawl_finished_at": _iso(crawl.finished_at),
            "crawl_finished_label": "",
            "analysed_at": _iso(crawl.analysed_at),
            "generated_at": datetime.now(UTC).isoformat(),
            "pages_analysed": score.pages_analysed if score else 0,
            "pages_crawled": crawl.pages_crawled,
        },
        "branding": dict(org.settings.get("report_branding") or {}),
        "health": {
            "overall": overall,
            "change": change,
            "previous_overall": previous.overall if previous else None,
            "categories": categories,
            "method": breakdown.get("method"),
            "weights_used": breakdown.get("overall", {}).get("weights_used", {}),
        },
        "crawl": {
            **crawl_facts,
            "pages_failed": crawl.pages_failed,
            "pages_blocked": crawl.pages_blocked,
            "robots_status": crawl.robots_status,
            "sitemap_url_count": crawl.sitemap_url_count,
            "warnings": crawl.warnings[:10],
            "config": {
                "max_pages": config.get("max_pages"),
                "max_depth": config.get("max_depth"),
                "delay_ms": config.get("delay_ms"),
                "user_agent": config.get("user_agent"),
            },
        },
        "counts": {
            "open_total": len(open_issues),
            "by_severity": by_severity,
            "ignored": sum(1 for i in issues if i.resolution_status == ResolutionStatus.IGNORED),
            "resolved": sum(1 for i in issues if i.resolution_status == ResolutionStatus.RESOLVED),
        },
        "critical": {
            "total": by_severity["critical"],
            "issues": [issue_facts(i) for i in open_issues if i.severity == Severity.CRITICAL][
                :PRIORITY_LIMIT
            ],
        },
        "high": {
            "total": by_severity["high"],
            "issues": [issue_facts(i) for i in open_issues if i.severity == Severity.HIGH][
                :PRIORITY_LIMIT
            ],
        },
        "categories": by_category,
        "internal_linking": {
            "orphan_pages": crawl_facts["orphan_pages"],
            "broken_internal_links": crawl_facts["broken_internal_links"],
            "suggestions_total": link_total,
            "suggestions": [
                {"source": s, "target": t, "anchor": a, "reason": r} for s, t, a, r in link_rows
            ],
        },
        "structured_data": {
            "pages_with_data": len({url for _, url in findings}),
            "blocks": len(findings),
            "invalid_blocks": len(invalid),
            "types": dict(sorted(types.items(), key=lambda kv: -kv[1])[:15]),
            "errors": [{"url": url, "errors": f.errors[:5]} for f, url in invalid[:SECTION_LIMIT]],
        },
        "changes": changes,
        "ai": await _ai_section(session, report, crawl),
        "action_plan": action_plan(open_issues),
        "methodology": {"rules": len(ALL_RULES), "limitations": LIMITATIONS},
    }
    return data
