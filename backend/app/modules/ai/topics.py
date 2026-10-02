"""The data a question is about, fetched before the model answers.

Small models seldom look things up on their own: given the generic top issues, they
answer "are there broken links?" with whatever ranks highest. So the code works out what a
question is about from its wording, and adds the matching open issues (or the page it
names) to the evidence first. When a topic has no open issues, the evidence says so, which
lets the model state that the latest crawl found none instead of guessing.

Detection is plain keyword matching on the question. It never decides the answer; it only
chooses which facts the model sees.
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select

from app.modules.ai.tools import (
    PageArgs,
    ToolContext,
    ToolError,
    get_page_details,
    issue_brief,
)
from app.modules.search_data.service import ai_evidence as search_evidence
from app.modules.seo.models import ResolutionStatus, SeoIssue

MAX_TOPICS = 3
ISSUES_PER_TOPIC = 8


@dataclass(frozen=True)
class Topic:
    label: str
    pattern: re.Pattern[str]
    rule_prefixes: tuple[str, ...]


def _topic(label: str, pattern: str, *prefixes: str) -> Topic:
    return Topic(label, re.compile(pattern, re.I), prefixes)


TOPICS: tuple[Topic, ...] = (
    _topic(
        "broken links and error pages",
        r"\bbroken\b|\b404\b|\b5\d\d\b|not found|dead links?|error pages?|"
        r"pages? (that )?(return|give|show)s? errors?|server errors?|fail(ed|ing)? to load",
        "tech.broken_internal_links",
        "tech.http_client_error",
        "tech.http_server_error",
        "tech.fetch_failed",
    ),
    _topic("titles", r"\btitles?\b", "onpage.title"),
    _topic("meta descriptions", r"\bmeta\b|\bdescriptions?\b", "onpage.meta_description"),
    _topic(
        "headings",
        r"\bh[1-6]\b|\bheadings?\b|\bheaders?\b",
        "onpage.h1",
        "onpage.heading_hierarchy",
    ),
    _topic(
        "images and alt text",
        r"\bimages?\b|\balt\b|\bpictures?\b|\bphotos?\b",
        "onpage.image_alt",
    ),
    _topic("redirects", r"\bredirect", "tech.redirect_chain", "tech.internal_link_to_redirect"),
    _topic(
        "canonical URLs and duplicate addresses",
        r"\bcanonical|duplicate (url|address)|url variants?",
        "onpage.canonical",
        "tech.canonical",
        "tech.duplicate_url_variants",
    ),
    _topic(
        "indexing, robots.txt and sitemaps",
        r"\bindex|\bnoindex\b|\brobots\b|\bsitemaps?\b|\bcrawlab|\bblocked\b|\bhttps\b",
        "tech.blocked_by_robots",
        "tech.unexpected_noindex",
        "tech.robots",
        "tech.sitemap",
        "tech.http_not_https",
    ),
    _topic(
        "page speed",
        r"\bslow\b|\bspeed\b|\bfast(er)?\b|load(ing)? times?|\bperformance\b|response times?",
        "tech.slow_response",
    ),
    _topic(
        "structured data",
        r"structured data|\bschema\b|rich (results?|snippets?)|json-?ld",
        "schema.",
    ),
    _topic(
        "internal links",
        r"internal links?|\borphan|\blinking\b|\binlinks?\b|\boutlinks?\b|\bnofollow\b|deep pages?",
        "links.",
        "tech.deep_important_page",
    ),
    _topic(
        "content",
        r"\bcontent\b|\bthin\b|word counts?|\bduplicate (pages?|text|content)\b|\bcopy\b",
        "content.",
    ),
    _topic("page language", r"\blang(uage)?\b", "onpage.lang_missing"),
    _topic("URL structure", r"url structure|\bslugs?\b|long urls?", "onpage.url_structure"),
)

# Data this platform does not hold. A question about it should say so first, instead of
# filling the answer with unrelated issues.
UNAVAILABLE: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "visitor numbers and traffic",
        re.compile(r"\bvisit(s|ors?)\b|\btraffic\b|\bsessions?\b|page ?views?|\baudience\b", re.I),
    ),
    (
        "search rankings and positions",
        re.compile(r"\brank(s|ed|ing|ings)?\b|position (on|in) (google|search)", re.I),
    ),
    ("competitors", re.compile(r"\bcompetitors?\b|\brivals?\b", re.I)),
    ("keywords and search volumes", re.compile(r"\bkeywords?\b|search volumes?", re.I)),
    ("backlinks", re.compile(r"\bbacklinks?\b|inbound links from other sites", re.I)),
    (
        "clicks, impressions and conversions",
        re.compile(r"\bclicks?\b|\bimpressions?\b|\bconversions?\b|bounce rate|\bctr\b", re.I),
    ),
)

# What Search Console data answers when it has been imported. Visitor totals,
# competitors, backlinks and search volumes stay unavailable: Search Console has
# Google Search clicks only, and no data about other sites.
COVERED_BY_SEARCH_DATA = frozenset(
    {"search rankings and positions", "clicks, impressions and conversions"}
)
SEARCH_DATA = re.compile(
    r"search console|\bgoogle\b|\bsearch (results?|performance|queries|terms)\b|\bqueries\b|"
    r"\bclicks?\b|\bimpressions?\b|\bctr\b|click-?through|\bposition\b|\brank|\bkeywords?\b|"
    r"\bvisit(s|ors?)\b|\btraffic\b",
    re.I,
)

# Questions about what to do next are answered from the overall priorities.
PRIORITY = re.compile(
    r"\bfirst\b|priorit|most important|next steps?|way forward|where (to|should (we|i)) start|"
    r"\bfocus\b|\burgent\b|\bbiggest\b|main (problems?|issues?)|what should (we|i) (do|fix)|"
    r"\bimprove\b",
    re.I,
)
_URL = re.compile(r"https?://[^\s'\"<>()]+|(?<![\w.])/[\w\-./%]*[\w\-/%]")


def topics_in(question: str) -> list[Topic]:
    return [t for t in TOPICS if t.pattern.search(question)][:MAX_TOPICS]


def unavailable_in(question: str) -> list[str]:
    return [label for label, pattern in UNAVAILABLE if pattern.search(question)]


def is_priority_question(question: str) -> bool:
    return bool(PRIORITY.search(question))


def page_in(question: str) -> str | None:
    match = _URL.search(question)
    return match.group(0).rstrip(".,;:!?") if match else None


async def _issues_for(ctx: ToolContext, topic: Topic) -> dict[str, Any]:
    matches = or_(*(SeoIssue.rule_id.startswith(p, autoescape=True) for p in topic.rule_prefixes))
    query = select(SeoIssue).where(
        SeoIssue.project_id == ctx.project.id,
        SeoIssue.organisation_id == ctx.org_id,
        SeoIssue.resolution_status == ResolutionStatus.OPEN,
        matches,
    )
    total = await ctx.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await ctx.session.scalars(
        query.order_by(SeoIssue.priority_score.desc()).limit(ISSUES_PER_TOPIC)
    )
    found: dict[str, Any] = {
        "topic": topic.label,
        "open_issues_total": total,
        "issues": [issue_brief(i) for i in rows],
    }
    if total == 0:
        # Worded so the model does not stretch "none found on the crawled pages" into
        # "none exist anywhere".
        found["note"] = (
            f"The latest analysed crawl found no open issues about {topic.label} on the "
            "pages it crawled. Say exactly that; do not claim more."
        )
    return found


async def evidence_for(ctx: ToolContext, question: str) -> dict[str, Any] | None:
    """The issues and page a question is about, or None when it names nothing specific."""
    found: dict[str, Any] = {}
    topics = topics_in(question)
    if topics:
        found["topics"] = [await _issues_for(ctx, t) for t in topics]
    url = page_in(question)
    if url:
        try:
            found["page"] = await get_page_details(ctx, PageArgs(url=url))
        except ToolError as exc:
            found["page"] = {"requested": url, "note": str(exc)}
    missing = unavailable_in(question)
    if SEARCH_DATA.search(question):
        search = await search_evidence(ctx.session, ctx.project)
        if search is not None:
            found["search_performance"] = search
            missing = [m for m in missing if m not in COVERED_BY_SEARCH_DATA]
    if missing:
        found["not_available"] = {
            "data": missing,
            "note": "This platform has no data on these. Start the answer by saying so in "
            "one sentence. Mention site issues only if the question also asks about them.",
        }
    if is_priority_question(question) and not topics and not missing:
        found["priorities"] = "Answer from top_open_issues, which is ordered by priority."
    return found or None


def focus_issue_ids(found: dict[str, Any] | None, top_open_issues: Any) -> set[str]:
    """Issues an answer to this question should cite."""
    ids: set[str] = set()
    if not found:
        return ids
    for topic in found.get("topics", []):
        ids |= {i["id"] for i in topic["issues"]}
    page = found.get("page") or {}
    ids |= {i["id"] for i in page.get("open_issues", [])}
    if "priorities" in found and isinstance(top_open_issues, dict):
        ids |= {i["id"] for i in top_open_issues.get("issues", [])}
    return ids
