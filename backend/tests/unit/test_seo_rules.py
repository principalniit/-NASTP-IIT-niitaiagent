"""Every rule: a case that triggers it, and a clean site that triggers nothing."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.crawler.models import FetchStatus
from app.modules.seo.analysis import run_rules
from app.modules.seo.context import AnalysisContext
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category, Severity
from app.modules.seo.rules import ALL_RULES
from tests.unit.seo_helpers import ROOT, context, link, page


def clean_site() -> list:  # type: ignore[type-arg]
    return [page("/"), page("/about"), page("/courses")]


def test_clean_site_has_no_findings() -> None:
    findings = run_rules(context(clean_site()))
    assert findings == [], [f.rule_id for f in findings]


def ids(ctx: AnalysisContext) -> set[str]:
    return {f.rule_id for f in run_rules(ctx)}


def build(mutate: Callable[[list], AnalysisContext]) -> AnalysisContext:  # type: ignore[type-arg]
    return mutate(clean_site())


def with_pages(*extra, **kw):  # type: ignore[no-untyped-def]
    def make(pages):  # type: ignore[no-untyped-def]
        return context(pages + [e() if callable(e) else e for e in extra], **kw)

    return make


def mutate_page(path: str, **changes):  # type: ignore[no-untyped-def]
    def make(pages):  # type: ignore[no-untyped-def]
        for p in pages:
            if p.url.endswith(path) and (path != "/" or p.url == ROOT):
                for k, v in changes.items():
                    setattr(p, k, v)
        return context(pages)

    return make


def broken_link_ctx(pages):  # type: ignore[no-untyped-def]
    missing = page("/gone", status_code=404, content_type="text/html", inlinks_count=1)
    ctx_pages = [*pages, missing]
    links = [link(pages[0], p) for p in pages[1:]] + [link(p, pages[0]) for p in pages[1:]]
    links.append(link(pages[1], missing))
    return context(ctx_pages, links)


def redirect_ctx(pages):  # type: ignore[no-untyped-def]
    old = page(
        "/old",
        status_code=301,
        final_url=ROOT + "about",
        content_type=None,
        inlinks_count=1,
        in_sitemap=False,
    )
    links = (
        [link(pages[0], p) for p in pages[1:]]
        + [link(p, pages[0]) for p in pages[1:]]
        + [link(pages[1], old)]
    )
    return context([*pages, old], links)


def chain_ctx(pages):  # type: ignore[no-untyped-def]
    pages[1].redirect_chain = [
        {"url": pages[1].url, "status_code": 301},
        {"url": ROOT + "x", "status_code": 302},
    ]
    return context(pages)


def canonical_problem_ctx(pages):  # type: ignore[no-untyped-def]
    bad = page("/bad", status_code=404, in_sitemap=False)
    pages[1].canonical_url = bad.url
    return context([*pages, bad])


def variants_ctx(pages):  # type: ignore[no-untyped-def]
    a = page("/Guide")
    b = page("/guide/", content_hash=a.content_hash)
    return context([*pages, a, b])


def duplicate_titles(pages):  # type: ignore[no-untyped-def]
    pages[1].title = pages[2].title = "Same title used on two different pages here"
    return context(pages)


def duplicate_descriptions(pages):  # type: ignore[no-untyped-def]
    pages[1].meta_description = pages[2].meta_description = (
        "The same description on two pages, which is long enough to pass."
    )
    return context(pages)


def duplicate_content(pages):  # type: ignore[no-untyped-def]
    pages[2].content_hash = pages[1].content_hash
    return context(pages)


def near_duplicate(pages):  # type: ignore[no-untyped-def]
    text = " ".join(f"alpha{i} beta gamma delta" for i in range(80))
    pages[1].text = text
    pages[2].text = text + " one extra word"
    return context(pages)


def topic_overlap(pages):  # type: ignore[no-untyped-def]
    pages[1].title = "Computer Science Degree Programme"
    pages[2].title = "Computer Science Degree Programme Overview"
    pages[1].headings = [
        {"level": 1, "text": "Computer Science Degree"},
        {"level": 2, "text": "a"},
        {"level": 2, "text": "b"},
    ]
    pages[2].headings = [
        {"level": 1, "text": "Computer Science Degree"},
        {"level": 2, "text": "a"},
        {"level": 2, "text": "b"},
    ]
    return context(pages)


def missing_sections(pages):  # type: ignore[no-untyped-def]
    return context(
        pages,
        settings={
            "content_types": [
                {
                    "key": "courses",
                    "label": "Courses",
                    "url_patterns": ["/courses"],
                    "expected_sections": ["Eligibility", "Details"],
                }
            ]
        },
    )


def schema_opportunity(pages):  # type: ignore[no-untyped-def]
    return context(
        pages,
        settings={
            "content_types": [
                {
                    "key": "courses",
                    "label": "Courses",
                    "url_patterns": ["/courses"],
                    "recommended_schema_types": ["Course"],
                }
            ]
        },
    )


def few_inlinks(pages):  # type: ignore[no-untyped-def]
    pages[1].inlinks_count = 1
    return context(pages, settings={"important_pages": ["/about"]})


def deep_important(pages):  # type: ignore[no-untyped-def]
    pages[1].depth = 6
    return context(pages, settings={"important_pages": ["/about"]})


def nofollow_internal(pages):  # type: ignore[no-untyped-def]
    links = [link(pages[0], p) for p in pages[1:]] + [link(p, pages[0]) for p in pages[1:]]
    links.append(link(pages[1], pages[2], nofollow=True))
    return context(pages, links)


def invalid_ld(pages):  # type: ignore[no-untyped-def]
    pages[1].structured_data = {
        "json_ld": [
            {"valid": False, "error": "Invalid JSON at line 1: x", "types": [], "data": None}
        ]
    }
    return context(pages)


def recommended_props(pages):  # type: ignore[no-untyped-def]
    pages[1].structured_data = {
        "json_ld": [
            {
                "valid": True,
                "error": None,
                "types": ["Course"],
                "data": {"@type": "Course", "name": "A", "description": "B"},
            }
        ]
    }
    return context(pages)


CASES: list[tuple[str, Callable[[list], AnalysisContext]]] = [  # type: ignore[type-arg]
    ("tech.http_client_error", broken_link_ctx),
    ("tech.http_server_error", with_pages(lambda: page("/err", status_code=503))),
    (
        "tech.fetch_failed",
        with_pages(
            lambda: page(
                "/t", fetch_status=FetchStatus.ERROR, status_code=None, error="Request timed out"
            )
        ),
    ),
    (
        "tech.http_not_https",
        lambda pages: context([page("http://example.org/")], root="http://example.org/"),
    ),
    ("tech.redirect_chain", chain_ctx),
    ("tech.internal_link_to_redirect", redirect_ctx),
    ("tech.broken_internal_links", broken_link_ctx),
    (
        "tech.sitemap_missing",
        lambda pages: context(
            pages,
            sitemaps=[{"url": ROOT + "sitemap.xml", "status": "not_found"}],
            sitemap_url_count=0,
        ),
    ),
    (
        "tech.sitemap_errors",
        lambda pages: context(
            pages,
            sitemaps=[
                {"url": "a", "status": "ok"},
                {"url": "b", "status": "error", "error": "bad"},
            ],
        ),
    ),
    ("tech.sitemap_bad_urls", with_pages(lambda: page("/gone", status_code=404, in_sitemap=True))),
    ("tech.robots_unreachable", lambda pages: context(pages, robots_status="unreachable")),
    ("tech.robots_missing", lambda pages: context(pages, robots_status="not_found")),
    (
        "tech.blocked_by_robots",
        with_pages(
            lambda: page("/private", fetch_status=FetchStatus.BLOCKED_BY_ROBOTS, status_code=None)
        ),
    ),
    ("tech.unexpected_noindex", mutate_page("/about", is_noindex=True)),
    ("tech.canonical_multiple", mutate_page("/about", canonical_count=2)),
    ("tech.canonical_target_problem", canonical_problem_ctx),
    ("tech.duplicate_url_variants", variants_ctx),
    ("tech.slow_response", mutate_page("/about", response_time_ms=1500)),
    ("tech.deep_important_page", deep_important),
    ("onpage.title_missing", mutate_page("/about", title=None, title_count=0)),
    ("onpage.title_multiple", mutate_page("/about", title_count=2)),
    ("onpage.title_length", mutate_page("/about", title="Short")),
    ("onpage.title_duplicate", duplicate_titles),
    (
        "onpage.meta_description_missing",
        mutate_page("/about", meta_description=None, meta_description_count=0),
    ),
    ("onpage.meta_description_multiple", mutate_page("/about", meta_description_count=2)),
    ("onpage.meta_description_length", mutate_page("/about", meta_description="Too short")),
    ("onpage.meta_description_duplicate", duplicate_descriptions),
    (
        "onpage.h1_missing",
        mutate_page(
            "/about", h1_count=0, headings=[{"level": 2, "text": "a"}, {"level": 2, "text": "b"}]
        ),
    ),
    (
        "onpage.h1_multiple",
        mutate_page(
            "/about",
            h1_count=2,
            headings=[
                {"level": 1, "text": "a"},
                {"level": 1, "text": "b"},
                {"level": 2, "text": "c"},
                {"level": 2, "text": "d"},
            ],
        ),
    ),
    (
        "onpage.heading_hierarchy",
        mutate_page(
            "/about",
            headings=[
                {"level": 1, "text": "a"},
                {"level": 3, "text": "b"},
                {"level": 2, "text": "c"},
            ],
        ),
    ),
    ("onpage.canonical_missing", mutate_page("/about", canonical_url=None, canonical_count=0)),
    ("onpage.url_structure", with_pages(lambda: page("/Some_Page"))),
    (
        "onpage.image_alt_missing",
        mutate_page(
            "/about",
            images_missing_alt=1,
            image_count=1,
            images=[{"src": "a.png", "alt": None, "has_alt": False}],
        ),
    ),
    ("onpage.lang_missing", mutate_page("/about", lang=None)),
    ("content.thin", mutate_page("/about", word_count=40)),
    ("content.duplicate", duplicate_content),
    ("content.near_duplicate", near_duplicate),
    ("content.topic_overlap", topic_overlap),
    (
        "content.weak_structure",
        mutate_page("/about", word_count=900, headings=[{"level": 1, "text": "a"}]),
    ),
    ("content.missing_sections", missing_sections),
    (
        "content.review_dated_reference",
        mutate_page("/about", title="Admissions open for the 2019 intake of students"),
    ),
    ("links.orphan", mutate_page("/about", is_orphan=True, inlinks_count=0)),
    ("links.important_few_inlinks", few_inlinks),
    ("links.no_internal_outlinks", mutate_page("/about", internal_links_count=0)),
    ("links.excessive", mutate_page("/about", internal_links_count=400)),
    ("links.nofollow_internal", nofollow_internal),
    ("schema.invalid", invalid_ld),
    ("schema.recommended_properties", recommended_props),
    (
        "schema.home_organisation_missing",
        mutate_page("/", structured_data={"json_ld": [], "microdata": {"count": 0, "types": []}}),
    ),
    ("schema.content_type_opportunity", schema_opportunity),
]


@pytest.mark.parametrize(("rule_id", "make"), CASES, ids=[c[0] for c in CASES])
def test_rule_fires_with_evidence_and_recommendation(rule_id: str, make) -> None:  # type: ignore[no-untyped-def]
    findings = [f for f in run_rules(build(make)) if f.rule_id == rule_id]
    assert findings, f"{rule_id} did not fire"
    for f in findings:
        assert f.evidence and f.recommendation and f.description
        assert f.affected_urls and f.affected_page_count >= 1


def test_every_rule_has_a_test_case() -> None:
    assert {r.id for r in ALL_RULES} == {rule_id for rule_id, _ in CASES}


def test_severity_escalates_for_home_and_important_pages() -> None:
    ctx = context([page("/", status_code=404), page("/a", status_code=404)])
    by_url = {
        f.affected_urls[0]: f for f in run_rules(ctx) if f.rule_id == "tech.http_client_error"
    }
    assert by_url[ROOT].severity == Severity.CRITICAL
    assert by_url[ROOT + "a"].severity == Severity.HIGH


def test_slow_response_severity_levels() -> None:
    ctx = context([page("/"), page("/a", response_time_ms=1200), page("/b", response_time_ms=5000)])
    found = {
        f.affected_urls[0]: f.severity for f in run_rules(ctx) if f.rule_id == "tech.slow_response"
    }
    assert found == {ROOT + "a": Severity.MEDIUM, ROOT + "b": Severity.HIGH}


def test_thresholds_come_from_project_settings() -> None:
    pages = [page("/"), page("/a", word_count=150)]
    assert "content.thin" in ids(context(pages))
    assert "content.thin" not in ids(
        context(pages, settings={"analysis": {"thresholds": {"thin_content_words": 100}}})
    )


def test_intentional_noindex_and_canonicalised_pages_are_not_flagged() -> None:
    ctx = context(
        [
            page("/"),
            page("/print", is_noindex=True, in_sitemap=False, title=None, meta_description=None),
            page("/dup", canonical_url=ROOT, meta_description=None),
        ]
    )
    found = ids(ctx)
    assert "tech.unexpected_noindex" not in found
    assert "onpage.meta_description_missing" not in found


def test_orphans_not_reported_when_page_limit_was_reached() -> None:
    pages = [page("/"), page("/a", is_orphan=True, inlinks_count=0)]
    assert "links.orphan" in ids(context(pages))
    assert "links.orphan" not in ids(context(pages, warnings=["The page limit (2) was reached"]))


def test_dated_reference_is_informational_and_skips_recent_years() -> None:
    ctx = context([page("/"), page("/a", title="Admissions for the 2025 academic session open")])
    assert "content.review_dated_reference" not in ids(ctx)
    ctx = context([page("/"), page("/a", title="Admissions for the 2021 academic session open")])
    f = next(f for f in run_rules(ctx) if f.rule_id == "content.review_dated_reference")
    assert f.severity == Severity.INFORMATIONAL and f.confidence == "low"


def test_structured_data_errors_and_enhancements_are_separate() -> None:
    ctx = build(recommended_props)
    findings = {f.rule_id: f for f in run_rules(ctx)}
    assert "schema.invalid" not in findings
    assert findings["schema.recommended_properties"].severity == Severity.INFORMATIONAL
    assert findings["schema.recommended_properties"].evidence["kind"] == "enhancement"


def test_finding_requires_evidence_and_recommendation() -> None:
    base = dict(
        rule_id="x.rule",
        category=Category.TECHNICAL,
        severity=Severity.LOW,
        scope="page",
        subject="s",
        title="Title",
        description="A description here",
        recommendation="Do this thing now",
        evidence={"a": 1},
        affected_urls=[ROOT],
        affected_page_count=1,
        confidence="high",
        effort="low",
    )
    Finding(**base)
    with pytest.raises(ValidationError):
        Finding(**{**base, "evidence": {}})
    with pytest.raises(ValidationError):
        Finding(**{**base, "recommendation": ""})


def test_engine_contains_no_institution_specific_logic() -> None:
    source = Path(__file__).resolve().parents[2] / "app" / "modules" / "seo"
    for file in source.rglob("*.py"):
        assert not re.search(r"niit|nastp", file.read_text(), re.IGNORECASE), file
