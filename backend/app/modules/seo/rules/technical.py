"""Technical SEO rules: availability, redirects, robots, sitemaps, canonicals, speed."""

from collections import defaultdict
from collections.abc import Iterable
from urllib.parse import urlsplit

from app.modules.crawler.models import FetchStatus
from app.modules.seo.context import AnalysisContext, PageData, group_subject
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules.base import Rule, escalate

T = Category.TECHNICAL


class ClientError(Rule):
    id = "tech.http_client_error"
    category, severity = T, Severity.HIGH
    title = "Page returns a client error (4xx)"
    description = (
        "Visitors and search engines following links to this URL get an error instead of "
        "content, and any links pointing here are wasted."
    )
    recommendation = (
        "Restore the page, or add a permanent (301) redirect to the most relevant live page, "
        "then update internal links that point to this URL."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.pages:
            if page.status_code and 400 <= page.status_code < 500:
                yield self.page_finding(
                    page,
                    {
                        "status_code": page.status_code,
                        "internal_pages_linking_here": page.inlinks_count,
                        "linked_from": ctx.linking_sources(page),
                        "in_sitemap": page.in_sitemap,
                    },
                    severity=escalate(ctx, page, Severity.HIGH, Severity.CRITICAL),
                )


class ServerError(Rule):
    id = "tech.http_server_error"
    category, severity = T, Severity.HIGH
    title = "Page returns a server error (5xx)"
    description = (
        "The server failed to deliver this page. Repeated server errors can cause search "
        "engines to crawl the site less and drop the page from results."
    )
    recommendation = (
        "Check the web server and application logs for this URL at the crawl time and fix "
        "the underlying error. Re-crawl to confirm the page returns 200."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.pages:
            if page.status_code and page.status_code >= 500:
                yield self.page_finding(
                    page,
                    {"status_code": page.status_code, "linked_from": ctx.linking_sources(page)},
                    severity=escalate(ctx, page, Severity.HIGH, Severity.CRITICAL),
                )


class FetchFailed(Rule):
    id = "tech.fetch_failed"
    category, severity = T, Severity.MEDIUM
    title = "Page could not be retrieved"
    description = (
        "The crawler could not obtain a response for this URL, for example because of a "
        "timeout, a connection failure or an oversized response."
    )
    recommendation = (
        "Open the URL yourself to confirm whether it loads. If it is slow or very large, "
        "reduce its size or server response time; if it fails, fix the server error."
    )
    confidence = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        failed = (FetchStatus.ERROR, FetchStatus.TOO_LARGE, FetchStatus.BLOCKED_DESTINATION)
        for page in ctx.pages:
            if page.fetch_status in failed:
                yield self.page_finding(
                    page,
                    {"outcome": page.fetch_status.value, "error": page.error or "No detail"},
                    severity=escalate(ctx, page, Severity.MEDIUM, Severity.HIGH),
                )


class InsecureHttp(Rule):
    id = "tech.http_not_https"
    category, severity = T, Severity.HIGH
    title = "Site is served over HTTP instead of HTTPS"
    description = (
        "The crawl reached pages over unencrypted HTTP. Browsers mark such pages as not "
        "secure and search engines prefer HTTPS."
    )
    recommendation = (
        "Serve the site over HTTPS with a valid certificate, redirect every HTTP URL to its "
        "HTTPS equivalent with a 301, and update the project root URL and internal links."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        http_pages = [p.url for p in ctx.pages if p.url.startswith("http://") and p.status_code]
        if ctx.root_url.startswith("http://"):
            yield self.site_finding(
                ctx, {"root_url": ctx.root_url, "http_pages_crawled": len(http_pages)}
            )
        elif http_pages:
            yield self.group_finding(
                group_subject(*http_pages),
                http_pages,
                {"root_url": ctx.root_url, "http_urls": http_pages[:20]},
                severity=Severity.MEDIUM,
                title="Internal pages are reached over HTTP",
                description="The site uses HTTPS, but some internal URLs were reached over HTTP.",
                recommendation=(
                    "Change internal links to use HTTPS and redirect these HTTP URLs to HTTPS "
                    "with a 301."
                ),
            )


class RedirectChain(Rule):
    id = "tech.redirect_chain"
    category, severity = T, Severity.MEDIUM
    title = "Redirect chain"
    description = (
        "This URL passes through more than one redirect before reaching content. Each hop "
        "slows visitors down and can dilute link signals."
    )
    recommendation = "Redirect this URL directly to the final destination in a single 301 step."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.pages:
            if len(page.redirect_chain) >= 2:
                hops = [
                    {"url": h["url"], "status_code": h["status_code"]} for h in page.redirect_chain
                ]
                yield self.page_finding(
                    page, {"hops": hops, "hop_count": len(hops), "final_url": page.final_url}
                )


class LinksToRedirect(Rule):
    id = "tech.internal_link_to_redirect"
    category, severity = T, Severity.LOW
    title = "Internal links point to a redirecting URL"
    description = (
        "Pages on the site link to a URL that redirects elsewhere, adding an unnecessary hop "
        "for every visitor and crawler."
    )
    recommendation = "Update these internal links to point directly at the redirect destination."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.pages:
            if page.is_redirect and page.inlinks_count > 0:
                yield self.page_finding(
                    page,
                    {
                        "status_code": page.status_code,
                        "redirects_to": page.final_url,
                        "linked_from": ctx.linking_sources(page),
                        "internal_pages_linking_here": page.inlinks_count,
                    },
                )


class BrokenLinksOnPage(Rule):
    id = "tech.broken_internal_links"
    category, severity = T, Severity.MEDIUM
    title = "Page contains broken internal links"
    description = "This page links to internal URLs that returned an error when crawled."
    recommendation = (
        "Remove these links or point them to working pages. Fixing the target pages also "
        "resolves this."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        failed = (FetchStatus.ERROR, FetchStatus.TOO_LARGE, FetchStatus.BLOCKED_DESTINATION)
        for page in ctx.pages:
            broken = []
            for link in ctx.outlinks.get(page.id, []):
                target = ctx.by_id.get(link.target_id) if link.target_id else None
                if (
                    link.is_internal
                    and target
                    and ((target.status_code or 0) >= 400 or target.fetch_status in failed)
                ):
                    broken.append(
                        {
                            "url": target.url,
                            "status_code": target.status_code,
                            "anchor_text": link.anchor_text,
                        }
                    )
            if broken:
                yield self.page_finding(page, {"broken_links": broken[:50], "count": len(broken)})


class SitemapMissing(Rule):
    id = "tech.sitemap_missing"
    category, severity = T, Severity.MEDIUM
    title = "No usable XML sitemap"
    description = (
        "No sitemap listing the site's pages was found. Sitemaps help search engines "
        "discover pages, especially ones with few internal links."
    )
    recommendation = (
        "Publish an XML sitemap of indexable pages (for example /sitemap.xml) and reference "
        "it from robots.txt with a 'Sitemap:' line."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        usable = [s for s in ctx.facts.sitemaps if s.get("status") == "ok"]
        if not usable or ctx.facts.sitemap_url_count == 0:
            yield self.site_finding(
                ctx,
                {
                    "sitemaps_checked": [
                        {"url": s["url"], "status": s.get("status"), "error": s.get("error")}
                        for s in ctx.facts.sitemaps
                    ]
                    or "No sitemap location was found in robots.txt; /sitemap.xml was not usable",
                    "urls_listed": ctx.facts.sitemap_url_count,
                },
            )


class SitemapErrors(Rule):
    id = "tech.sitemap_errors"
    category, severity = T, Severity.MEDIUM
    title = "Sitemap could not be read"
    description = "One or more sitemap files returned an error or were not valid sitemaps."
    recommendation = "Fix the listed sitemap files so each returns 200 and valid sitemap XML."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        broken = [s for s in ctx.facts.sitemaps if s.get("status") == "error"]
        if broken and any(s.get("status") == "ok" for s in ctx.facts.sitemaps):
            yield self.site_finding(
                ctx, {"sitemaps": [{"url": s["url"], "error": s.get("error")} for s in broken]}
            )


class SitemapListsBadUrls(Rule):
    id = "tech.sitemap_bad_urls"
    category, severity = T, Severity.MEDIUM
    title = "Sitemap lists URLs that should not be indexed"
    description = (
        "The sitemap includes URLs that return errors, redirect, are marked noindex, or "
        "declare a different canonical URL. Sitemaps should list only final, indexable URLs."
    )
    recommendation = "Remove these URLs from the sitemap or replace them with their final URLs."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        bad: list[dict[str, object]] = []
        for page in ctx.pages:
            if not page.in_sitemap:
                continue
            reason = None
            if page.status_code and page.status_code >= 400:
                reason = f"returns {page.status_code}"
            elif page.is_redirect:
                reason = f"redirects ({page.status_code}) to {page.final_url}"
            elif page.analysable and page.is_noindex:
                reason = "is marked noindex"
            elif page.analysable and page.canonicalised_elsewhere:
                reason = f"declares canonical {page.canonical_url}"
            if reason:
                bad.append({"url": page.url, "reason": reason})
        if bad:
            urls = [str(b["url"]) for b in bad]
            yield self.group_finding(group_subject(*urls), urls, {"urls": bad[:50]})


class RobotsUnreachable(Rule):
    id = "tech.robots_unreachable"
    category, severity = T, Severity.CRITICAL
    title = "robots.txt could not be fetched"
    description = (
        "robots.txt returned a server error or could not be reached. Under RFC 9309 crawlers "
        "must then treat the whole site as disallowed, so search engines may stop crawling it."
    )
    recommendation = (
        "Make /robots.txt return 200 (or 404 if you want no rules) reliably, then re-crawl."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        if ctx.facts.robots_status == "unreachable":
            yield self.site_finding(
                ctx, {"robots_status": "unreachable", "warnings": ctx.facts.warnings}
            )


class RobotsMissing(Rule):
    id = "tech.robots_missing"
    category, severity = T, Severity.INFORMATIONAL
    title = "No robots.txt file"
    description = (
        "The site has no robots.txt. This is allowed and means everything may be crawled, "
        "but the file is the standard place to point crawlers to the sitemap."
    )
    recommendation = "Add a minimal robots.txt that allows crawling and lists the sitemap URL."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        if ctx.facts.robots_status == "not_found":
            yield self.site_finding(ctx, {"robots_status": "not_found"})


class BlockedByRobots(Rule):
    id = "tech.blocked_by_robots"
    category, severity = T, Severity.LOW
    title = "Linked page is blocked by robots.txt"
    description = (
        "This URL is linked from the site or listed in the sitemap, but robots.txt forbids "
        "crawling it, so search engines cannot read its content."
    )
    recommendation = (
        "If the page should appear in search results, remove the matching Disallow rule. If "
        "it should stay private, remove it from the sitemap and prominent links."
    )
    confidence = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.pages:
            if page.fetch_status == FetchStatus.BLOCKED_BY_ROBOTS and (
                page.in_sitemap or page.inlinks_count > 0 or ctx.is_important(page.url)
            ):
                yield self.page_finding(
                    page,
                    {
                        "in_sitemap": page.in_sitemap,
                        "linked_from": ctx.linking_sources(page),
                        "important_page": ctx.is_important(page.url),
                    },
                    severity=Severity.HIGH
                    if ctx.is_important(page.url) or page.in_sitemap
                    else Severity.LOW,
                )


class UnexpectedNoindex(Rule):
    id = "tech.unexpected_noindex"
    category, severity = T, Severity.HIGH
    title = "Important or sitemap-listed page is marked noindex"
    description = (
        "This page tells search engines not to index it, yet it is listed in the sitemap or "
        "configured as important. This is often accidental."
    )
    recommendation = (
        "If the page should appear in search results, remove 'noindex' from the meta robots "
        "tag or X-Robots-Tag header. Otherwise remove it from the sitemap."
    )
    confidence = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.is_noindex and (page.in_sitemap or ctx.is_important(page.url)):
                yield self.page_finding(
                    page,
                    {
                        "meta_robots": page.meta_robots,
                        "x_robots_tag": page.x_robots_tag,
                        "in_sitemap": page.in_sitemap,
                        "important_page": ctx.is_important(page.url),
                    },
                    severity=escalate(ctx, page, Severity.HIGH, Severity.CRITICAL),
                )


class MultipleCanonicals(Rule):
    id = "tech.canonical_multiple"
    category, severity = T, Severity.HIGH
    title = "Page declares more than one canonical URL"
    description = "Conflicting canonical tags make search engines ignore all of them."
    recommendation = "Keep exactly one rel=canonical link in the page head."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if page.canonical_count > 1:
                yield self.page_finding(
                    page,
                    {
                        "canonical_count": page.canonical_count,
                        "first_canonical": page.canonical_url,
                    },
                )


class CanonicalTargetProblem(Rule):
    id = "tech.canonical_target_problem"
    category, severity = T, Severity.HIGH
    title = "Canonical URL points to a problem page"
    description = (
        "The canonical URL declared by this page returns an error, redirects, is blocked, or "
        "is itself marked noindex, so the canonical signal is unreliable."
    )
    recommendation = "Point the canonical tag at the final, working, indexable version of the page."

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            if not page.canonicalised_elsewhere or page.canonical_url is None:
                continue
            target = ctx.by_url.get(page.canonical_url)
            if target is None:
                if urlsplit(page.canonical_url).hostname not in ctx.config.allowed_hosts:
                    yield self.page_finding(
                        page,
                        {"canonical_url": page.canonical_url, "reason": "points to another domain"},
                        severity=Severity.INFORMATIONAL,
                        title="Canonical URL points to another domain",
                        description=(
                            "The page names a URL on a different domain as its canonical, which "
                            "asks search engines to index that domain instead."
                        ),
                        recommendation=(
                            "Confirm this is intended (for example syndicated content). If not, "
                            "point the canonical to this page or its preferred version here."
                        ),
                    )
                continue
            reason = None
            if target.status_code and target.status_code >= 400:
                reason = f"canonical URL returns {target.status_code}"
            elif target.is_redirect:
                reason = f"canonical URL redirects to {target.final_url}"
            elif target.fetch_status == FetchStatus.BLOCKED_BY_ROBOTS:
                reason = "canonical URL is blocked by robots.txt"
            elif target.analysable and target.is_noindex:
                reason = "canonical URL is marked noindex"
            if reason:
                yield self.page_finding(
                    page, {"canonical_url": page.canonical_url, "reason": reason}
                )


def variant_key(url: str) -> str:
    parts = urlsplit(url)
    path = (parts.path or "/").lower().rstrip("/") or "/"
    return f"{parts.scheme}://{(parts.hostname or '').lower()}{path}"


class DuplicateUrlVariants(Rule):
    id = "tech.duplicate_url_variants"
    category, severity = T, Severity.MEDIUM
    title = "Same content is served at several URL variants"
    description = (
        "These URLs differ only by letter case, a trailing slash or query parameters, yet "
        "serve identical content, splitting signals between duplicates."
    )
    recommendation = (
        "Choose one URL form, redirect the others to it with a 301 (or add a canonical tag "
        "pointing to it), and use that form in internal links."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        groups: dict[tuple[str, str], list[PageData]] = defaultdict(list)
        for page in ctx.indexable_pages:
            if page.content_hash:
                groups[(variant_key(page.url), page.content_hash)].append(page)
        for (key, _), pages in groups.items():
            if len(pages) > 1:
                urls = [p.url for p in pages]
                yield self.group_finding(
                    group_subject(key), urls, {"variant_of": key, "urls": urls}
                )


class SlowResponse(Rule):
    id = "tech.slow_response"
    category, severity = T, Severity.MEDIUM
    title = "Slow server response"
    description = (
        "The server took a long time to start responding to this URL. This was measured once "
        "from the crawler's location and is not a Core Web Vitals measurement."
    )
    recommendation = (
        "Investigate server-side performance for this page (caching, database queries, "
        "hosting capacity) and re-crawl to confirm."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        t = ctx.thresholds
        for page in ctx.pages:
            ms = page.response_time_ms
            if ms is None or ms < t.slow_response_ms or page.is_redirect:
                continue
            yield self.page_finding(
                page,
                {
                    "response_time_ms": ms,
                    "threshold_ms": t.slow_response_ms,
                    "very_slow_threshold_ms": t.very_slow_response_ms,
                    "sample_size": 1,
                },
                severity=Severity.HIGH if ms >= t.very_slow_response_ms else Severity.MEDIUM,
            )


class DeepImportantPage(Rule):
    id = "tech.deep_important_page"
    category, severity = T, Severity.MEDIUM
    title = "Important page is many clicks from the home page"
    description = (
        "This page is configured as important but needs several clicks to reach from the home "
        "page, which reduces how often it is crawled and how much weight it receives."
    )
    recommendation = "Link to this page from the home page, main navigation or a hub page."
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.thresholds.max_important_depth
        for page in ctx.analysable_pages:
            deep = page.depth is None or page.depth > limit
            if page.url != ctx.root_url and ctx.is_important(page.url) and deep:
                yield self.page_finding(
                    page,
                    {
                        "depth": page.depth if page.depth is not None else "not reachable by links",
                        "max_depth": limit,
                    },
                )


RULES: list[Rule] = [
    ClientError(), ServerError(), FetchFailed(), InsecureHttp(), RedirectChain(),
    LinksToRedirect(), BrokenLinksOnPage(), SitemapMissing(), SitemapErrors(),
    SitemapListsBadUrls(), RobotsUnreachable(), RobotsMissing(), BlockedByRobots(),
    UnexpectedNoindex(), MultipleCanonicals(), CanonicalTargetProblem(), DuplicateUrlVariants(),
    SlowResponse(), DeepImportantPage(),
]  # fmt: skip
