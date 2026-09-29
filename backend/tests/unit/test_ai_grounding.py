"""Grounding checks, protected-fact detection and outline rendering."""

from app.modules.ai.grounding import check_output, numbers_in, terminology_warnings
from app.modules.ai.outputs import (
    ContentOutlineOutput,
    IssueExplanationOutput,
    ManagementSummaryOutput,
)
from app.modules.ai.tasks import issue_ids_in, render_outline
from app.modules.drafts.protected import protected_reasons

ISSUE = "0b7c1e7e-8a55-4c55-9a55-1f2b3c4d5e6f"
EVIDENCE = {
    "issues": [
        {
            "id": ISSUE,
            "rule_id": "onpage.title_missing",
            "title": "Missing title",
            "affected_page_count": 12,
            "priority": 71.5,
        }
    ],
    "score": {"overall": 64.0},
}


def explanation(text: str, ids: list[str] | None = None) -> IssueExplanationOutput:
    return IssueExplanationOutput(
        explanation=text,
        why_it_matters="Titles describe the page to search engines and visitors.",
        steps=["Add a unique title to each page."],
        how_to_verify="Run a new crawl.",
        issue_ids=ids if ids is not None else [ISSUE],
    )


def test_grounded_output_passes() -> None:
    output = explanation("12 pages have no title. The site health score is 64.")
    report = check_output(output, EVIDENCE, issue_ids_in(EVIDENCE))
    assert report.passed, report.violations


def test_numbers_not_in_evidence_are_violations() -> None:
    report = check_output(explanation("40 pages have no title."), EVIDENCE, issue_ids_in(EVIDENCE))
    assert not report.passed and "40" in report.violations[0]


def test_unknown_issue_ids_are_violations() -> None:
    other = "11111111-2222-3333-4444-555555555555"
    report = check_output(
        explanation("Pages have no title.", [other]), EVIDENCE, issue_ids_in(EVIDENCE)
    )
    assert report.violations == [f"Refers to issues that were not provided: {other}"]


def test_uuids_do_not_count_as_numbers() -> None:
    assert numbers_in(f"see issue {ISSUE}") == set()
    assert numbers_in({"a": [1, 2.50, "3,000 and 4.0"], "b": True}) == {"1", "2.5", "3000", "4"}


def test_forbidden_claims_are_violations() -> None:
    claims = [
        "Fixing this guarantees better results.",
        "The page could reach position 3.",
        "It will get you to the first page of Google.",
        "The search volume of this keyword is high.",
        "Expect 12 more visitors each day.",
        "Traffic will increase once titles are fixed.",
    ]
    for claim in claims:
        report = check_output(explanation(claim), EVIDENCE, issue_ids_in(EVIDENCE))
        assert any("unsupported claim" in v for v in report.violations), claim


def test_every_text_field_is_checked() -> None:
    output = ManagementSummaryOutput(
        headline="Site health overview",
        overview="The latest crawl found issues.",
        key_findings=[{"statement": "Titles are missing.", "issue_ids": [ISSUE]}],
        priorities=[{"action": "Add titles", "reason": "Affects 99 pages.", "issue_ids": []}],
        data_limitations=["No ranking data."],
    )
    report = check_output(output, EVIDENCE, issue_ids_in(EVIDENCE))
    assert report.violations == ["Uses numbers that are not in the project data: 99"]


def test_terminology_warnings() -> None:
    terms = [{"preferred": "NIIT", "avoid": ["Niit", "N.I.I.T"]}]
    assert terminology_warnings(["Study at N.I.I.T today"], terms) == [
        "Uses 'N.I.I.T'; the approved term is 'NIIT'"
    ]
    assert terminology_warnings(["Study at NIITians"], terms) == []


def test_protected_reasons() -> None:
    assert protected_reasons("About the programme", "About our programme") == []
    reasons = protected_reasons(None, "Apply before 15 March 2026. Fee: Rs. 50,000")
    joined = " ".join(reasons)
    assert "rs. 50,000" in joined and "2026" in joined and "15 march" in joined
    assert "fee" in joined
    removed = protected_reasons("Classes start in 2025", "Classes start soon")
    assert removed == ["Removes or changes factual values: 2025"]
    assert protected_reasons("x", "Eligibility: see the prospectus") == [
        "Mentions official topics: eligibility"
    ]
    assert protected_reasons(None, "Minimum CGPA applies") == ["Introduces factual values: cgpa"]


def test_outline_marks_facts_to_verify() -> None:
    output = ContentOutlineOutput(
        purpose="Help applicants apply.",
        sections=[
            {
                "heading": "How to apply",
                "points": ["List the steps."],
                "facts_needed": ["[verify: application deadline]", "required documents"],
            }
        ],
        questions_for_editor=["Who approves the deadline?"],
    )
    text = render_outline(output)
    assert "## How to apply" in text
    assert "- [verify: application deadline]" in text
    assert "- [verify: required documents]" in text
    assert text.endswith("- Who approves the deadline?")
