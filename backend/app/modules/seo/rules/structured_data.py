"""Structured data rules. Errors and optional enhancements are reported separately."""

from collections import defaultdict
from collections.abc import Iterable

from app.modules.seo.context import AnalysisContext, group_subject
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules.base import Rule
from app.modules.seo.schema_check import ORGANISATION_TYPES, check_page, page_types

S = Category.STRUCTURED_DATA


class InvalidStructuredData(Rule):
    id = "schema.invalid"
    category, severity = S, Severity.HIGH
    title = "Structured data contains errors"
    description = (
        "The page's JSON-LD is invalid or missing properties required for its type, so search "
        "engines may ignore it."
    )
    recommendation = (
        "Fix the listed errors and re-check the markup with a structured data validator."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            checks = check_page(page.structured_data)
            errors = [
                {"format": c.format, "types": c.types, "error": e} for c in checks for e in c.errors
            ]
            if errors:
                invalid_json = any(e.startswith("Invalid JSON") for c in checks for e in c.errors)
                yield self.page_finding(
                    page,
                    {"errors": errors[:20], "kind": "error"},
                    severity=Severity.HIGH if invalid_json else Severity.MEDIUM,
                )


class RecommendedProperties(Rule):
    id = "schema.recommended_properties"
    category, severity = S, Severity.INFORMATIONAL
    title = "Structured data could include recommended properties"
    description = (
        "The markup is valid, but adding recommended properties can make the page eligible "
        "for richer search results. This is an optional enhancement, not an error."
    )
    recommendation = (
        "Add the listed properties where accurate values exist in approved content. Never add "
        "values that are not verified."
    )
    confidence = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for page in ctx.analysable_pages:
            warnings = sorted(
                {
                    w
                    for c in check_page(page.structured_data)
                    if c.format == "json_ld"
                    for w in c.warnings
                    if "recommended" in w
                }
            )
            if warnings:
                yield self.page_finding(page, {"suggestions": warnings[:20], "kind": "enhancement"})


class HomeOrganisationMissing(Rule):
    id = "schema.home_organisation_missing"
    category, severity = S, Severity.LOW
    title = "Home page has no Organization structured data"
    description = (
        "Organization markup (or a subtype such as EducationalOrganization) on the home page "
        "helps search engines connect the site to the organisation's name, logo and profiles."
    )
    recommendation = (
        "Add JSON-LD for Organization or the most specific subtype to the home page, using "
        "only verified details such as the official name, URL and logo."
    )

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        home = ctx.by_url.get(ctx.root_url)
        if home and home.analysable:
            types = page_types(home.structured_data)
            if not types & ORGANISATION_TYPES:
                yield self.page_finding(
                    home, {"types_found": sorted(types) or "none", "kind": "opportunity"}
                )


class ContentTypeSchemaOpportunity(Rule):
    id = "schema.content_type_opportunity"
    category, severity = S, Severity.INFORMATIONAL
    title = "Pages could use structured data for their content type"
    description = (
        "These pages match a configured content type whose usual schema.org type is not "
        "present. Adding it is an optional enhancement."
    )
    recommendation = (
        "Add JSON-LD of the suggested type to these pages, filled only with verified details "
        "from the page and approved sources."
    )
    confidence = "medium"
    effort = "medium"

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        wanted = {ct.key: ct for ct in ctx.settings.content_types if ct.recommended_schema_types}
        if not wanted:
            return
        missing: dict[str, list[str]] = defaultdict(list)
        for page in ctx.indexable_pages:
            present = page_types(page.structured_data)
            for key in ctx.content_types_for(page.url):
                ct = wanted.get(key)
                if ct and not set(ct.recommended_schema_types) & present:
                    missing[key].append(page.url)
        for key, urls in missing.items():
            ct = wanted[key]
            yield self.group_finding(
                group_subject("schema-type", key),
                urls,
                {
                    "content_type": ct.label,
                    "suggested_types": ct.recommended_schema_types,
                    "urls": urls[:50],
                    "kind": "opportunity",
                },
                title=f"{ct.label} pages lack {' or '.join(ct.recommended_schema_types)} markup",
            )


RULES: list[Rule] = [
    InvalidStructuredData(), RecommendedProperties(), HomeOrganisationMissing(),
    ContentTypeSchemaOpportunity(),
]  # fmt: skip
