"""Internal linking rules."""

from collections.abc import Iterable

from app.modules.seo.context import AnalysisContext
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules.base import Rule, escalate

L = Category.INTERNAL_LINKING


class OrphanPage(Rule):
    id = "links.orphan"
    category, severity = L, Severity.MEDIUM
    title = "Orphan page: listed in the sitemap but not linked"
    description = (
        "No crawled page links to this page; it was found only through the sitemap. Visitors "
        "cannot navigate to it and search engines treat it as less important."
    )
    recommendation = (
        "Link to this page from relevant pages (see Internal Linking suggestions), or remove "
        "it from the sitemap if it is no longer needed."
    )
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        if ctx.facts.page_limit_reached:
            return  # unvisited pages might link here
        for page in ctx.pages:
            if page.is_orphan:
                yield self.page_finding(
                    page,
                    {"in_sitemap": True, "internal_pages_linking_here": 0},
                    severity=escalate(ctx, page, Severity.MEDIUM, Severity.HIGH),
                )


class ImportantFewInlinks(Rule):
    id = "links.important_few_inlinks"
    category, severity = L, Severity.MEDIUM
    title = "Important page has few internal links"
    description = (
        "This page is configured as important, but few other pages link to it, which limits "
        "how easily visitors and search engines find it."
    )
    recommendation = "Add contextual links to this page from related pages and hub pages."
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        if ctx.facts.page_limit_reached:
            return
        minimum = ctx.thresholds.min_inlinks_important
        for page in ctx.analysable_pages:
            if (
                page.url != ctx.root_url
                and ctx.is_important(page.url)
                and page.inlinks_count < minimum
            ):
                yield self.page_finding(
                    page,
                    {
                        "internal_pages_linking_here": page.inlinks_count,
                        "minimum": minimum,
                        "linked_from": ctx.linking_sources(page),
                    },
                )


class NoInternalOutlinks(Rule):
    id = "links.no_internal_outlinks"
    category, severity = L, Severity.LOW
    title = "Page has no links to other pages on the site"
    description = "A page with no internal links is a dead end for visitors and crawlers."
    recommendation = "Add links to related pages, the parent section or the home page."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.internal_links_count == 0:
                yield self.page_finding(
                    page, {"internal_links": 0, "external_links": page.external_links_count}
                )


class ExcessiveLinks(Rule):
    id = "links.excessive"
    category, severity = L, Severity.LOW
    title = "Page has a very large number of links"
    description = "Very many links dilute the importance of each one and make the page hard to use."
    recommendation = (
        "Reduce links to the most useful ones, for example by grouping them into section pages."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.thresholds.max_links_per_page
        for page in ctx.analysable_pages:
            total = page.internal_links_count + page.external_links_count
            if total > limit:
                yield self.page_finding(
                    page,
                    {
                        "links": total,
                        "internal": page.internal_links_count,
                        "external": page.external_links_count,
                        "threshold": limit,
                    },
                )


class NofollowInternal(Rule):
    id = "links.nofollow_internal"
    category, severity = L, Severity.LOW
    title = "Internal links marked nofollow"
    description = (
        "Links to your own pages marked rel=nofollow ask search engines not to follow them, "
        "which is rarely intended for internal navigation."
    )
    recommendation = 'Remove rel="nofollow" from internal links unless there is a specific reason.'

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            targets = sorted(
                {
                    link.target_url
                    for link in ctx.outlinks.get(page.id, [])
                    if link.is_internal and link.nofollow
                }
            )
            if targets:
                yield self.page_finding(
                    page, {"nofollow_internal_links": targets[:30], "count": len(targets)}
                )


RULES: list[Rule] = [
    OrphanPage(), ImportantFewInlinks(), NoInternalOutlinks(), ExcessiveLinks(), NofollowInternal(),
]  # fmt: skip
