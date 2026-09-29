"""Content rules: thin, duplicate, near-duplicate and overlapping content, structure,
expected sections and date-based editorial review flags."""

import re
from collections import defaultdict
from collections.abc import Iterable

from app.modules.seo.context import AnalysisContext, PageData, group_subject
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules.base import Rule
from app.modules.seo.rules.technical import variant_key
from app.modules.seo.text import (
    common_title_suffix,
    connected_groups,
    near_duplicate_pairs,
    simhash,
    strip_suffix,
    tokens,
)

C = Category.CONTENT
_YEAR = re.compile(r"\b(19[5-9]\d|20\d\d)\b")


class ThinContent(Rule):
    id = "content.thin"
    category, severity = C, Severity.LOW
    title = "Page has little text content"
    description = (
        "The page has few words of visible text. Short pages can be fine (for example a "
        "contact page) but often do not answer visitors' questions fully."
    )
    recommendation = (
        "Check whether the page fully covers its topic. If not, add useful, accurate content "
        "from approved sources; if the page is not needed, merge it into a related page."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.thresholds.thin_content_words
        for page in ctx.indexable_pages:
            words = page.word_count or 0
            if words < limit:
                yield self.page_finding(
                    page,
                    {"word_count": words, "threshold": limit},
                    severity=Severity.MEDIUM if words < limit / 2 else Severity.LOW,
                )


class DuplicateContent(Rule):
    id = "content.duplicate"
    category, severity = C, Severity.MEDIUM
    title = "Pages have identical content"
    description = (
        "These pages have the same visible text. Search engines usually show only one of them "
        "and may not pick the one you prefer."
    )
    recommendation = (
        "Keep one page. Redirect the others to it with a 301, or add a canonical tag pointing "
        "to it if the duplicates must stay available."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        groups: dict[str, list[PageData]] = defaultdict(list)
        for page in ctx.indexable_pages:
            if page.content_hash and (page.word_count or 0) > 0:
                groups[page.content_hash].append(page)
        for digest, pages in groups.items():
            # URL variants of one page are reported by tech.duplicate_url_variants.
            if len(pages) > 1 and len({variant_key(p.url) for p in pages}) > 1:
                urls = [p.url for p in pages]
                yield self.group_finding(
                    group_subject("content", digest),
                    urls,
                    {"urls": urls, "word_count": pages[0].word_count, "content_hash": digest},
                )


class NearDuplicateContent(Rule):
    id = "content.near_duplicate"
    category, severity = C, Severity.LOW
    title = "Pages have nearly identical content"
    description = (
        "These pages share almost all of their text. They may compete with each other in "
        "search results."
    )
    recommendation = (
        "Make each page's content distinct, or merge them into one page and redirect the others."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        hashes: dict[str, int] = {}
        exact: dict[str, str | None] = {}
        for page in ctx.indexable_pages:
            value = simhash(page.text)
            if value is not None:
                hashes[page.url] = value
                exact[page.url] = page.content_hash
        pairs = [
            (a, b, d)
            for a, b, d in near_duplicate_pairs(hashes)
            if exact[a] != exact[b]  # identical pages are reported by content.duplicate
        ]
        similarity = {(a, b): round(100 * (64 - d) / 64) for a, b, d in pairs}
        for urls in connected_groups((a, b) for a, b, _ in pairs):
            members = set(urls)
            yield self.group_finding(
                group_subject("near", *urls),
                urls,
                {
                    "urls": urls,
                    "pairs": [
                        {"a": a, "b": b, "fingerprint_similarity_percent": s}
                        for (a, b), s in similarity.items()
                        if a in members
                    ][:20],
                    "method": "64-bit simhash over 3-word shingles, at most 3 bits different",
                },
            )


class TopicOverlap(Rule):
    id = "content.topic_overlap"
    category, severity = C, Severity.LOW
    title = "Pages target the same topic"
    description = (
        "These pages have nearly the same title and main heading but different content, so "
        "they may compete for the same searches."
    )
    recommendation = (
        "Differentiate the pages' titles and headings to reflect their distinct purposes, or "
        "consolidate them into one stronger page."
    )
    confidence = "low"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        pages = ctx.indexable_pages
        suffix = common_title_suffix(p.title for p in pages)
        topics: dict[str, set[str]] = {}
        for page in pages:
            words = set(tokens(strip_suffix(page.title, suffix))) | {
                w for h in page.headings if h.get("level") == 1 for w in tokens(h.get("text"))
            }
            if len(words) >= 2:
                topics[page.url] = words
        by_url = ctx.by_url
        pairs: list[tuple[str, str]] = []
        urls = sorted(topics)
        for i, a in enumerate(urls[:1500]):
            for b in urls[i + 1 : 1500]:
                if by_url[a].content_hash == by_url[b].content_hash:
                    continue
                union = topics[a] | topics[b]
                if union and len(topics[a] & topics[b]) / len(union) >= 0.8:
                    pairs.append((a, b))
        for group in connected_groups(pairs):
            yield self.group_finding(
                group_subject("topic", *group),
                group,
                {
                    "pages": [{"url": u, "title": by_url[u].title} for u in group],
                    "method": "title and H1 word overlap of at least 80 percent",
                },
            )


class WeakStructure(Rule):
    id = "content.weak_structure"
    category, severity = C, Severity.LOW
    title = "Long page with few subheadings"
    description = "Long text without subheadings is hard to scan for readers and search engines."
    recommendation = "Break the content into sections with descriptive H2 and H3 headings."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.indexable_pages:
            subheadings = sum(1 for h in page.headings if int(h.get("level", 0)) >= 2)
            if (page.word_count or 0) >= 400 and subheadings < 2:
                yield self.page_finding(
                    page, {"word_count": page.word_count, "subheadings": subheadings}
                )


class MissingSections(Rule):
    id = "content.missing_sections"
    category, severity = C, Severity.LOW
    title = "Expected sections not found"
    description = (
        "This page matches a configured content type, but some sections expected for that type "
        "were not found among its headings. This is an editorial suggestion, not an error."
    )
    recommendation = (
        "Check whether visitors need the missing information. If so, add it as a clearly "
        "headed section using verified content."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        types = {ct.key: ct for ct in ctx.settings.content_types if ct.expected_sections}
        if not types:
            return
        for page in ctx.analysable_pages:
            headings = " \n ".join(h.get("text", "") for h in page.headings).lower()
            for key in ctx.content_types_for(page.url):
                ct = types.get(key)
                if ct is None:
                    continue
                missing = [s for s in ct.expected_sections if s.lower() not in headings]
                if missing:
                    finding = self.page_finding(
                        page,
                        {
                            "content_type": ct.label,
                            "missing_sections": missing,
                            "headings_found": [h.get("text") for h in page.headings[:20]],
                        },
                    )
                    finding.subject = group_subject(page.url, key)
                    yield finding


class OutdatedIndicator(Rule):
    id = "content.review_dated_reference"
    category, severity = C, Severity.INFORMATIONAL
    title = "Title or heading mentions an earlier year"
    description = (
        "The page's title or main heading refers to a year before last year. This does not "
        "mean the content is out of date; it is flagged for editorial review only."
    )
    recommendation = (
        "Ask the content owner to confirm whether the page is still current. Update it from "
        "approved sources, or mark it clearly as archived if it is historical."
    )
    confidence = "low"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        if ctx.facts.finished_at is None:
            return
        cutoff = ctx.facts.finished_at.year - 1
        for page in ctx.indexable_pages:
            texts = {"title": page.title or ""}
            h1 = next((h["text"] for h in page.headings if h.get("level") == 1), "")
            texts["h1"] = h1 or ""
            found = {
                where: sorted({y for y in _YEAR.findall(text) if int(y) < cutoff})
                for where, text in texts.items()
            }
            found = {k: v for k, v in found.items() if v}
            if found:
                yield self.page_finding(
                    page, {"years_mentioned": found, "crawl_year": ctx.facts.finished_at.year}
                )


RULES: list[Rule] = [
    ThinContent(), DuplicateContent(), NearDuplicateContent(), TopicOverlap(), WeakStructure(),
    MissingSections(), OutdatedIndicator(),
]  # fmt: skip
