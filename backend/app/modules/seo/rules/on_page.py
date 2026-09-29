"""On-page rules: titles, meta descriptions, headings, canonicals, URLs, images, language."""

import re
from collections import defaultdict
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit

from app.modules.seo.context import AnalysisContext, PageData, group_subject
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules.base import Rule, escalate

OP = Category.ON_PAGE


class TitleMissing(Rule):
    id = "onpage.title_missing"
    category, severity = OP, Severity.HIGH
    title = "Page has no title"
    description = (
        "The title is the main text search engines show for a page. Without one, a title is "
        "guessed from other content."
    )
    recommendation = (
        "Add a unique, descriptive <title> that states what the page is about, ideally "
        "between the configured minimum and maximum length."
    )
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if not page.title:
                yield self.page_finding(
                    page,
                    {"title_tags_found": page.title_count, "first_h1": _first_h1(page)},
                    severity=escalate(ctx, page, Severity.HIGH, Severity.CRITICAL),
                )


class TitleMultiple(Rule):
    id = "onpage.title_multiple"
    category, severity = OP, Severity.MEDIUM
    title = "Page has more than one title tag"
    description = "Several <title> tags make it unclear which one search engines will use."
    recommendation = "Keep a single <title> in the page head."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.title_count > 1:
                yield self.page_finding(
                    page, {"title_tags_found": page.title_count, "first_title": page.title}
                )


class TitleLength(Rule):
    id = "onpage.title_length"
    category, severity = OP, Severity.LOW
    title = "Title length outside the recommended range"
    description = (
        "Long titles are usually cut off in search results; very short titles often fail to "
        "describe the page."
    )
    recommendation = "Rewrite the title so the key information fits within the recommended length."
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        t = ctx.thresholds
        for page in ctx.analysable_pages:
            if not page.title:
                continue
            n = len(page.title)
            if n > t.title_max_chars or n < t.title_min_chars:
                too_long = n > t.title_max_chars
                yield self.page_finding(
                    page,
                    {
                        "title": page.title,
                        "length": n,
                        "min": t.title_min_chars,
                        "max": t.title_max_chars,
                    },
                    title="Title is too long" if too_long else "Title is too short",
                    recommendation=(
                        f"Shorten the title to about {t.title_max_chars} characters, keeping the "
                        "most important words first."
                        if too_long
                        else f"Expand the title to at least {t.title_min_chars} characters so it "
                        "clearly describes the page."
                    ),
                )


def _normalised(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


class DuplicateTitle(Rule):
    id = "onpage.title_duplicate"
    category, severity = OP, Severity.MEDIUM
    title = "Several pages share the same title"
    description = (
        "Identical titles make pages look interchangeable to search engines and to people "
        "choosing a result."
    )
    recommendation = "Give each page a unique title that reflects its specific content."
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        groups: dict[str, list[PageData]] = defaultdict(list)
        for page in ctx.indexable_pages:
            if page.title:
                groups[_normalised(page.title)].append(page)
        for value, pages in groups.items():
            if len(pages) > 1:
                urls = [p.url for p in pages]
                yield self.group_finding(
                    group_subject("title", value), urls, {"title": pages[0].title, "urls": urls}
                )


class DescriptionMissing(Rule):
    id = "onpage.meta_description_missing"
    category, severity = OP, Severity.MEDIUM
    title = "Page has no meta description"
    description = (
        "Search engines often use the meta description as the summary under the title. "
        "Without one, they pick text from the page, which may not represent it well."
    )
    recommendation = "Add a meta description that summarises the page in one or two sentences."
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.indexable_pages:
            if not page.meta_description:
                yield self.page_finding(
                    page, {"meta_description_tags_found": page.meta_description_count}
                )


class DescriptionMultiple(Rule):
    id = "onpage.meta_description_multiple"
    category, severity = OP, Severity.LOW
    title = "Page has more than one meta description"
    description = "Several meta description tags make it unclear which one will be used."
    recommendation = "Keep a single meta description tag."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.meta_description_count > 1:
                yield self.page_finding(
                    page, {"meta_description_tags_found": page.meta_description_count}
                )


class DescriptionLength(Rule):
    id = "onpage.meta_description_length"
    category, severity = OP, Severity.LOW
    title = "Meta description length outside the recommended range"
    description = "Long descriptions are cut off in search results; short ones say little."
    recommendation = "Rewrite the description to fit the recommended length."
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        t = ctx.thresholds
        for page in ctx.indexable_pages:
            if not page.meta_description:
                continue
            n = len(page.meta_description)
            if n > t.description_max_chars or n < t.description_min_chars:
                too_long = n > t.description_max_chars
                yield self.page_finding(
                    page,
                    {
                        "meta_description": page.meta_description,
                        "length": n,
                        "min": t.description_min_chars,
                        "max": t.description_max_chars,
                    },
                    title="Meta description is too long"
                    if too_long
                    else "Meta description is too short",
                )


class DuplicateDescription(Rule):
    id = "onpage.meta_description_duplicate"
    category, severity = OP, Severity.LOW
    title = "Several pages share the same meta description"
    description = "Repeated descriptions do not help people tell the pages apart in results."
    recommendation = "Write a specific description for each page."
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        groups: dict[str, list[PageData]] = defaultdict(list)
        for page in ctx.indexable_pages:
            if page.meta_description:
                groups[_normalised(page.meta_description)].append(page)
        for value, pages in groups.items():
            if len(pages) > 1:
                urls = [p.url for p in pages]
                yield self.group_finding(
                    group_subject("description", value),
                    urls,
                    {"meta_description": pages[0].meta_description, "urls": urls},
                )


def _first_h1(page: PageData) -> str | None:
    return next((h["text"] for h in page.headings if h.get("level") == 1), None)


class H1Missing(Rule):
    id = "onpage.h1_missing"
    category, severity = OP, Severity.MEDIUM
    title = "Page has no H1 heading"
    description = "The H1 is the page's main visible heading and helps readers and search engines."
    recommendation = "Add one H1 that states the page's main topic."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.h1_count == 0:
                yield self.page_finding(
                    page,
                    {
                        "headings_found": [
                            f"H{h['level']}: {h['text']}" for h in page.headings[:10]
                        ],
                        "title": page.title,
                    },
                )


class H1Multiple(Rule):
    id = "onpage.h1_multiple"
    category, severity = OP, Severity.LOW
    title = "Page has more than one H1"
    description = "Several H1 headings blur which topic is the page's main one."
    recommendation = "Keep one H1 for the main topic and use H2 to H6 for sections."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.h1_count > 1:
                h1s = [h["text"] for h in page.headings if h.get("level") == 1]
                yield self.page_finding(page, {"h1_count": page.h1_count, "h1_texts": h1s[:10]})


class HeadingHierarchy(Rule):
    id = "onpage.heading_hierarchy"
    category, severity = OP, Severity.LOW
    title = "Heading levels are skipped"
    description = (
        "Headings jump levels (for example from H1 to H3), which makes the outline harder to "
        "follow for screen readers and search engines."
    )
    recommendation = "Use heading levels in order, without skipping levels."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            skips: list[str] = []
            previous = 0
            for heading in page.headings:
                level = int(heading.get("level", 0))
                if previous and level > previous + 1:
                    skips.append(f"H{previous} → H{level}: {heading.get('text', '')}"[:200])
                previous = level
            if skips:
                yield self.page_finding(page, {"skipped_levels": skips[:10]})


class CanonicalMissing(Rule):
    id = "onpage.canonical_missing"
    category, severity = OP, Severity.LOW
    title = "Page has no canonical tag"
    description = (
        "A self-referencing canonical tag protects a page against duplicates created by "
        "tracking parameters or alternative URLs."
    )
    recommendation = 'Add <link rel="canonical" href="..."> with the page\'s preferred URL.'
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.indexable_pages:
            if page.canonical_count == 0:
                yield self.page_finding(page, {"canonical_tags_found": 0})


class UrlStructure(Rule):
    id = "onpage.url_structure"
    category, severity = OP, Severity.LOW
    title = "URL is hard to read or share"
    description = (
        "Short, lower-case, hyphenated URLs are easier to read, share and remember, and are "
        "less likely to be duplicated."
    )
    recommendation = (
        "Where practical, use short lower-case paths with hyphens, and redirect old URLs with "
        "301s if you change them. Changing URLs has a cost, so prioritise new pages."
    )
    confidence = "medium"
    effort = "high"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.thresholds.max_url_length
        for page in ctx.indexable_pages:
            parts = urlsplit(page.url)
            path = unquote(parts.path)
            problems = []
            if len(page.url) > limit:
                problems.append(f"longer than {limit} characters ({len(page.url)})")
            if path != path.lower():
                problems.append("contains upper-case letters")
            if "_" in path:
                problems.append("uses underscores instead of hyphens")
            if " " in path:
                problems.append("contains spaces")
            if "//" in parts.path:
                problems.append("contains repeated slashes")
            if parts.query and len(parts.query.split("&")) > 3:
                problems.append("has more than three query parameters")
            if problems:
                yield self.page_finding(page, {"url": page.url, "problems": problems})


class ImageAltMissing(Rule):
    id = "onpage.image_alt_missing"
    category, severity = OP, Severity.LOW
    title = "Images without alt attributes"
    description = (
        "Images without an alt attribute are invisible to screen-reader users and give "
        'search engines no description. Decorative images should use an empty alt="".'
    )
    recommendation = (
        'Add descriptive alt text to informative images, and alt="" to purely decorative ones.'
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.images_missing_alt:
                sources = [i["src"] for i in page.images if not i.get("has_alt")][:20]
                yield self.page_finding(
                    page,
                    {
                        "images_without_alt": page.images_missing_alt,
                        "total_images": page.image_count,
                        "examples": sources,
                    },
                    severity=Severity.MEDIUM if page.images_missing_alt >= 5 else Severity.LOW,
                )


class LangMissing(Rule):
    id = "onpage.lang_missing"
    category, severity = OP, Severity.LOW
    title = "Page does not declare its language"
    description = (
        "The html lang attribute tells browsers, screen readers and search engines which "
        "language the page is in."
    )
    recommendation = 'Add a lang attribute to the <html> element, for example lang="en".'
    auto_fix_eligible = True

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if not page.lang:
                yield self.page_finding(page, {"html_lang": None})


RULES: list[Rule] = [
    TitleMissing(), TitleMultiple(), TitleLength(), DuplicateTitle(), DescriptionMissing(),
    DescriptionMultiple(), DescriptionLength(), DuplicateDescription(), H1Missing(), H1Multiple(),
    HeadingHierarchy(), CanonicalMissing(), UrlStructure(), ImageAltMissing(), LangMissing(),
]  # fmt: skip
