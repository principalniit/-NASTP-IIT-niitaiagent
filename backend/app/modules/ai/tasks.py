"""AI tasks. Each gathers evidence with the read-only tools, then defines what the model
must produce and what happens with a grounded result."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.grounding import terminology_warnings
from app.modules.ai.models import AIAnalysis, AIKind, SeoRecommendation
from app.modules.ai.outputs import (
    ContentOutlineOutput,
    IssueExplanationOutput,
    ManagementSummaryOutput,
    MetadataDraftOutput,
    PagePlanOutput,
)
from app.modules.ai.tools import (
    IssueArgs,
    IssuesArgs,
    NoArgs,
    OptionalPageArgs,
    PageArgs,
    RuleArgs,
    ToolContext,
    ToolError,
    compare_latest_crawls,
    get_internal_links,
    get_issue_evidence,
    get_page_details,
    get_project_summary,
    get_rule,
    get_schema_findings,
    get_seo_issues,
)
from app.modules.drafts.models import DraftField, DraftSource
from app.modules.drafts.service import new_draft
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.search_data.service import page_performance
from app.modules.users.models import User

TITLE_RULES = {
    "onpage.title_missing",
    "onpage.title_multiple",
    "onpage.title_length",
    "onpage.title_duplicate",
}
DESCRIPTION_RULES = {
    "onpage.meta_description_missing", "onpage.meta_description_multiple",
    "onpage.meta_description_length", "onpage.meta_description_duplicate",
}  # fmt: skip


def _as[OutputT: BaseModel](output: BaseModel, cls: type[OutputT]) -> OutputT:
    if not isinstance(output, cls):
        raise TypeError(f"Expected {cls.__name__}, got {type(output).__name__}")
    return output


@dataclass
class TaskPlan:
    task: str
    evidence: dict[str, Any]
    schema: type[BaseModel]
    crawl_id: uuid.UUID | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskEnv:
    session: AsyncSession
    tools: ToolContext
    analysis: AIAnalysis
    org_settings: OrganisationSettings
    project_settings: ProjectSettingsData
    requester: User | None


def issue_ids_in(evidence: Any) -> set[str]:
    """Ids of every issue included in the evidence."""
    found: set[str] = set()
    if isinstance(evidence, dict):
        if "rule_id" in evidence and "id" in evidence:
            found.add(str(evidence["id"]))
        for value in evidence.values():
            found |= issue_ids_in(value)
    elif isinstance(evidence, list):
        for item in evidence:
            found |= issue_ids_in(item)
    return found


async def _latest_crawl_id(env: TaskEnv) -> uuid.UUID:
    return (await env.tools.latest_crawl()).id


# ---------------------------------------------------------------- management summary


async def plan_summary(env: TaskEnv) -> TaskPlan:
    summary = await get_project_summary(env.tools, NoArgs())
    if summary["latest_analysed_crawl"] is None:
        raise ToolError("This project has no analysed crawl yet. Crawl and analyse it first.")
    issues = await get_seo_issues(env.tools, IssuesArgs(limit=15))
    try:
        comparison: Any = await compare_latest_crawls(env.tools, NoArgs())
    except ToolError as exc:
        comparison = f"No comparison available: {exc}"
    return TaskPlan(
        task=(
            "Write a short management summary of this website's SEO health for institutional "
            "leadership who are not SEO specialists. Explain the most important findings and the "
            "recommended priorities in plain language, citing issue references. Mention what changed since "
            "the previous crawl only if a comparison is provided. List data limitations, including "
            "that the score is a site-health indicator and not a search ranking."
        ),
        evidence={"project_summary": summary, "top_open_issues": issues, "comparison": comparison},
        schema=ManagementSummaryOutput,
        crawl_id=await _latest_crawl_id(env),
    )


# ---------------------------------------------------------------- issue explanation


async def plan_issue(env: TaskEnv) -> TaskPlan:
    issue_id = uuid.UUID(str(env.analysis.subject_id))
    issue = await get_issue_evidence(env.tools, IssueArgs(issue_id=issue_id))
    evidence: dict[str, Any] = {
        "issue": issue,
        "rule": await get_rule(env.tools, RuleArgs(rule_id=issue["rule_id"])),
    }
    if issue.get("affected_url"):
        try:
            page = await get_page_details(env.tools, PageArgs(url=issue["affected_url"]))
            page.pop("open_issues", None)
            evidence["page"] = page
        except ToolError:
            pass
    return TaskPlan(
        task=(
            "Explain this issue to a website editor in plain language: what was found, why it "
            "matters, the concrete steps to fix it on this site, and how to verify the fix (a new "
            "crawl). Put the issue reference in issue_ids."
        ),
        evidence=evidence,
        schema=IssueExplanationOutput,
    )


async def finish_issue(env: TaskEnv, plan: TaskPlan, output: BaseModel) -> None:
    output = _as(output, IssueExplanationOutput)
    issue = plan.evidence["issue"]
    env.session.add(
        SeoRecommendation(
            organisation_id=env.analysis.organisation_id,
            project_id=env.analysis.project_id,
            ai_analysis_id=env.analysis.id,
            issue_ids=[issue["id"]],
            page_url=issue.get("affected_url"),
            title=f"How to fix: {issue['title']}"[:300],
            body=output.explanation,
            steps=output.steps,
        )
    )


# ---------------------------------------------------------------- page plan


async def _page_evidence(env: TaskEnv) -> dict[str, Any]:
    url = str(env.analysis.params.get("page_url"))
    page = await get_page_details(env.tools, PageArgs(url=url))
    links = await get_internal_links(env.tools, PageArgs(url=url))
    schema = await get_schema_findings(env.tools, OptionalPageArgs(url=url))
    return {"page": page, "links": links, "structured_data": schema}


async def plan_page(env: TaskEnv) -> TaskPlan:
    evidence = await _page_evidence(env)
    return TaskPlan(
        task=(
            "Suggest specific improvements for this page, based only on its open issues and the page "
            "facts. Each improvement must name the area and cite the related issue references."
        ),
        evidence=evidence,
        schema=PagePlanOutput,
        crawl_id=await _latest_crawl_id(env),
    )


def _terminology(env: TaskEnv, texts: list[str]) -> list[str]:
    """Reviewer warnings for terms the organisation asked to avoid."""
    terms = [e.model_dump() for e in env.org_settings.approved_terminology]
    return terminology_warnings(texts, terms)


def _warn(env: TaskEnv, warnings: list[str]) -> None:
    env.analysis.grounding = {**env.analysis.grounding, "warnings": warnings}


async def finish_page(env: TaskEnv, plan: TaskPlan, output: BaseModel) -> None:
    output = _as(output, PagePlanOutput)
    _warn(env, _terminology(env, [i.suggestion for i in output.improvements]))
    url = plan.evidence["page"]["url"]
    for item in output.improvements:
        env.session.add(
            SeoRecommendation(
                organisation_id=env.analysis.organisation_id,
                project_id=env.analysis.project_id,
                ai_analysis_id=env.analysis.id,
                issue_ids=item.issue_ids,
                page_url=url,
                title=f"{item.area.replace('_', ' ').capitalize()}: {url}"[:300],
                body=item.suggestion,
            )
        )


# ---------------------------------------------------------------- metadata draft


async def plan_metadata(env: TaskEnv) -> TaskPlan:
    t = env.project_settings.analysis.thresholds
    page = await get_page_details(env.tools, PageArgs(url=str(env.analysis.params.get("page_url"))))
    page["open_issues"] = [
        i for i in page["open_issues"] if i["rule_id"] in TITLE_RULES | DESCRIPTION_RULES
    ]
    queries = await search_queries_for(env, page["url"])
    task = (
        f"Draft a page title of {t.title_min_chars} to {t.title_max_chars} characters and a meta "
        f"description of {t.description_min_chars} to {t.description_max_chars} characters for "
        "this page. Describe only what the page text and headings say. Do not add facts, "
        "figures, dates or claims that are not in the page. In facts_used, quote the phrases "
        "from the page you relied on."
    )
    if queries:
        task += (
            " search_queries lists what people typed into Google when this page appeared. "
            "Where the page text covers a query, prefer its wording, so searchers recognise the "
            "page. Never add a topic the page does not cover."
        )
    return TaskPlan(
        task=task,
        evidence={
            "page": page,
            **({"search_queries": queries} if queries else {}),
            "limits": t.model_dump(
                include={
                    "title_min_chars",
                    "title_max_chars",
                    "description_min_chars",
                    "description_max_chars",
                }
            ),
        },
        schema=MetadataDraftOutput,
        crawl_id=await _latest_crawl_id(env),
    )


async def search_queries_for(env: TaskEnv, url: str) -> list[str]:
    """Google queries the page appeared for, from imported Search Console data.

    Queries with digits are left out: they often carry years, fees or figures, and a
    draft must take those from the page itself, never from what people searched for.
    """
    data = await page_performance(env.session, env.tools.project, url, 90)
    if data["state"] != "ready":
        return []
    return [q["query"] for q in data["top_queries"] if not any(c.isdigit() for c in q["query"])]


def metadata_warnings(env: TaskEnv, output: MetadataDraftOutput) -> list[str]:
    t = env.project_settings.analysis.thresholds
    warnings = []
    if not t.title_min_chars <= len(output.title) <= t.title_max_chars:
        warnings.append(
            f"Title is {len(output.title)} characters (target {t.title_min_chars}-{t.title_max_chars})"
        )
    if not t.description_min_chars <= len(output.meta_description) <= t.description_max_chars:
        warnings.append(
            f"Meta description is {len(output.meta_description)} characters "
            f"(target {t.description_min_chars}-{t.description_max_chars})"
        )
    return warnings + _terminology(env, [output.title, output.meta_description])


async def finish_metadata(env: TaskEnv, plan: TaskPlan, output: BaseModel) -> None:
    output = _as(output, MetadataDraftOutput)
    page = plan.evidence["page"]
    warnings = metadata_warnings(env, output)
    _warn(env, warnings)
    pairs = [
        (DraftField.TITLE, page.get("title"), output.title, TITLE_RULES),
        (
            DraftField.META_DESCRIPTION,
            page.get("meta_description"),
            output.meta_description,
            DESCRIPTION_RULES,
        ),
    ]
    for field_name, original, proposed, rules in pairs:
        if (original or "").strip() == proposed.strip():
            continue
        await new_draft(
            env.session,
            project=env.tools.project,
            page_url=page["url"],
            field=field_name,
            original=original,
            proposed=proposed,
            reason=output.rationale,
            evidence={
                "issue_ids": [i["id"] for i in page["open_issues"] if i["rule_id"] in rules],
                "facts_used": output.facts_used,
                "warnings": warnings,
            },
            source=DraftSource.AI,
            author=None,
            ai_analysis_id=env.analysis.id,
        )


# ---------------------------------------------------------------- content outline


async def plan_outline(env: TaskEnv) -> TaskPlan:
    evidence = await _page_evidence(env)
    url = evidence["page"]["url"]
    types = [
        {"label": ct.label, "expected_sections": ct.expected_sections}
        for ct in env.project_settings.content_types
        if ct.key in _content_types_for(env, url)
    ]
    profile = env.project_settings.institutional_profile
    evidence["content_type"] = types or "No content type is configured for this page."
    evidence["approved_sources"] = [s.model_dump() for s in profile.approved_sources]
    goal = env.analysis.params.get("goal")
    return TaskPlan(
        task=(
            "Propose an improved content outline for this page: its purpose and a list of sections "
            "with headings and the points each should cover, using only information already on the "
            "page. Where a section needs facts that are not in the evidence (dates, fees, eligibility, "
            "requirements, figures), list them in facts_needed as [verify: ...] items instead of "
            "writing them. Add questions for the editor where information is missing."
            + (f" Editor's goal: {goal}" if goal else "")
        ),
        evidence=evidence,
        schema=ContentOutlineOutput,
        crawl_id=await _latest_crawl_id(env),
    )


def _content_types_for(env: TaskEnv, url: str) -> list[str]:
    import fnmatch
    from urllib.parse import urlsplit

    path = urlsplit(url).path or "/"
    return [
        ct.key
        for ct in env.project_settings.content_types
        if any(fnmatch.fnmatchcase(path, p) for p in ct.url_patterns)
    ]


def render_outline(output: ContentOutlineOutput) -> str:
    lines = [f"Purpose: {output.purpose}", ""]
    for section in output.sections:
        lines.append(f"## {section.heading}")
        lines.extend(f"- {point}" for point in section.points)
        lines.extend(
            f"- [verify: {fact.removeprefix('[verify:').rstrip(']').strip()}]"
            for fact in section.facts_needed
        )
        lines.append("")
    if output.questions_for_editor:
        lines.append("Questions for the editor:")
        lines.extend(f"- {q}" for q in output.questions_for_editor)
    return "\n".join(lines).strip()


async def finish_outline(env: TaskEnv, plan: TaskPlan, output: BaseModel) -> None:
    output = _as(output, ContentOutlineOutput)
    page = plan.evidence["page"]
    current = "\n".join(page.get("headings") or []) or None
    texts = [output.purpose] + [s.heading for s in output.sections]
    texts += [p for s in output.sections for p in s.points]
    warnings = _terminology(env, texts)
    _warn(env, warnings)
    await new_draft(
        env.session,
        project=env.tools.project,
        page_url=page["url"],
        field=DraftField.CONTENT_OUTLINE,
        original=current,
        proposed=render_outline(output),
        reason="Content outline proposed by the AI assistant from the page's own content and issues.",
        evidence={
            "issue_ids": [i["id"] for i in page.get("open_issues", [])][:20],
            "warnings": warnings,
        },
        source=DraftSource.AI,
        author=None,
        ai_analysis_id=env.analysis.id,
    )


async def _nothing(env: TaskEnv, plan: TaskPlan, output: BaseModel) -> None:
    return None


PlanFn = Callable[[TaskEnv], Awaitable[TaskPlan]]
FinishFn = Callable[[TaskEnv, TaskPlan, BaseModel], Awaitable[None]]

TASKS: dict[AIKind, tuple[PlanFn, FinishFn]] = {
    AIKind.MANAGEMENT_SUMMARY: (plan_summary, _nothing),
    AIKind.ISSUE_EXPLANATION: (plan_issue, finish_issue),
    AIKind.PAGE_PLAN: (plan_page, finish_page),
    AIKind.METADATA_DRAFT: (plan_metadata, finish_metadata),
    AIKind.CONTENT_OUTLINE: (plan_outline, finish_outline),
}
