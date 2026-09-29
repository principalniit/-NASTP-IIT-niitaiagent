from app.modules.seo.analysis import run_rules
from app.modules.seo.link_opportunities import suggest_links
from app.modules.seo.priority import prioritise
from app.modules.seo.schema_check import check_page
from app.modules.seo.scoring import compute_score
from app.modules.seo.text import common_title_suffix, hamming, near_duplicate_pairs, simhash
from tests.unit.seo_helpers import ROOT, context, link, page


def test_clean_site_scores_100() -> None:
    ctx = context([page("/"), page("/a")])
    score = compute_score(ctx, run_rules(ctx))
    assert score.overall == 100.0
    assert set(score.categories.values()) == {100.0}


def test_site_wide_critical_issue_zeroes_the_category() -> None:
    ctx = context([page("/"), page("/a")], robots_status="unreachable")
    score = compute_score(ctx, run_rules(ctx))
    assert score.categories["technical"] == 0.0
    assert score.overall == 70.0  # technical weighs 30 percent
    contribution = score.breakdown["categories"]["technical"]["contributions"][0]
    assert contribution["rule_id"] == "tech.robots_unreachable"


def test_page_share_scales_the_penalty() -> None:
    pages = [page("/")] + [page(f"/p{i}") for i in range(9)]
    pages[1].meta_description = None
    pages[1].meta_description_count = 0
    ctx = context(pages)
    score = compute_score(ctx, run_rules(ctx))
    # medium (0.2) x 1 of 10 pages = 0.02 penalty
    assert score.categories["on_page"] == 98.0


def test_categories_without_analysable_pages_are_not_scored() -> None:
    ctx = context([page("/", status_code=500)])
    score = compute_score(ctx, run_rules(ctx))
    assert score.categories["on_page"] is None
    assert score.categories["technical"] is not None
    assert score.overall == score.categories["technical"]


def test_custom_weights() -> None:
    ctx = context(
        [page("/"), page("/a")],
        robots_status="unreachable",
        settings={
            "analysis": {
                "category_weights": {
                    "technical": 50,
                    "on_page": 50,
                    "content": 0,
                    "internal_linking": 0,
                    "structured_data": 0,
                }
            }
        },
    )
    assert compute_score(ctx, run_rules(ctx)).overall == 50.0


def test_priority_rewards_important_pages_and_explains_itself() -> None:
    ctx = context([page("/", title=None, title_count=0), page("/a", title=None, title_count=0)])
    findings = {
        f.affected_urls[0]: f for f in run_rules(ctx) if f.rule_id == "onpage.title_missing"
    }
    home_score, home_factors = prioritise(ctx, findings[ROOT])
    other_score, _ = prioritise(ctx, findings[ROOT + "a"])
    assert home_score > other_score
    assert {f["factor"] for f in home_factors} == {
        "severity",
        "reach",
        "page importance",
        "effort",
        "confidence",
    }
    assert 0 <= other_score <= 100


def test_simhash_band_search_finds_close_pairs_only() -> None:
    base = " ".join(f"w{i} common words here" for i in range(100))
    a, b = simhash(base), simhash(base + " extra")
    c = simhash(" ".join(f"z{i} other text there" for i in range(100)))
    assert a is not None and b is not None and c is not None
    assert hamming(a, b) <= 3 < hamming(a, c)
    pairs = near_duplicate_pairs({"a": a, "b": b, "c": c})
    assert [(x, y) for x, y, _ in pairs] == [("a", "b")]
    assert simhash("too short") is None


def test_common_title_suffix() -> None:
    titles = ["Home | Example", "About | Example", "Courses | Example", "Other"]
    assert common_title_suffix(titles) == " | Example"
    assert common_title_suffix(["A", "B"]) is None


def test_link_suggestions_require_a_real_mention() -> None:
    home = page("/", text="Welcome. Read about our Scholarship Opportunities for new students.")
    target = page(
        "/funding",
        headings=[{"level": 1, "text": "Scholarship Opportunities"}],
        inlinks_count=0,
        is_orphan=True,
    )
    unrelated = page("/labs", text="Our laboratories are open daily.")
    ctx = context([home, target, unrelated], links=[link(home, unrelated), link(unrelated, home)])
    suggestions = suggest_links(ctx)
    assert [(s.source.url, s.target.url) for s in suggestions] == [(ROOT, ROOT + "funding")]
    assert "Scholarship Opportunities" in suggestions[0].snippet
    # Once linked, no suggestion is made.
    ctx = context([home, target, unrelated], links=[link(home, target), link(home, unrelated)])
    assert suggest_links(ctx) == []


def test_generic_headings_do_not_produce_suggestions() -> None:
    home = page("/", text="Please contact us for more information.")
    target = page(
        "/contact",
        headings=[{"level": 1, "text": "Contact us"}],
        inlinks_count=0,
        title="Contact us",
    )
    assert suggest_links(context([home, target], links=[])) == []


def test_schema_checks() -> None:
    ok = {
        "json_ld": [
            {
                "valid": True,
                "types": ["Event"],
                "data": {
                    "@graph": [
                        {
                            "@type": "Event",
                            "name": "Open day",
                            "startDate": "2026-10-01",
                            "location": "Campus",
                        }
                    ]
                },
            }
        ]
    }
    checks = check_page(ok)
    assert checks[0].valid and any("endDate" in w for w in checks[0].warnings)
    missing = {
        "json_ld": [{"valid": True, "types": ["Event"], "data": {"@type": "Event", "name": "X"}}]
    }
    assert {
        "Event is missing required property 'startDate'",
        "Event is missing required property 'location'",
    } <= set(check_page(missing)[0].errors)
    untyped = {"json_ld": [{"valid": True, "types": [], "data": {"name": "x"}}]}
    assert not check_page(untyped)[0].valid
    unknown = {"json_ld": [{"valid": True, "types": ["Thing"], "data": {"@type": "Thing"}}]}
    assert check_page(unknown)[0].valid and check_page(unknown)[0].errors == []


def test_severity_dominates_page_importance() -> None:
    from app.modules.seo.models import Severity

    pages = [page("/", title="Short"), page("/other", status_code=404)]
    ctx = context(pages)
    findings = {f.rule_id: f for f in run_rules(ctx)}
    low_on_home, _ = prioritise(ctx, findings["onpage.title_length"])
    high_elsewhere, _ = prioritise(ctx, findings["tech.http_client_error"])
    assert findings["onpage.title_length"].severity == Severity.LOW
    assert findings["tech.http_client_error"].severity == Severity.HIGH
    assert high_elsewhere > low_on_home
