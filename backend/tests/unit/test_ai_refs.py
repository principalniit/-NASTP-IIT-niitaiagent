"""Short issue references keep small models from mistyping long ids."""

from app.modules.ai.outputs import AgentAnswer
from app.modules.ai.refs import IssueRefs

A = "a6d3ce00-b9b3-460a-9daa-a53fb9621f6e"
B = "11111111-2222-3333-4444-555555555555"


def test_evidence_is_shortened_and_output_expanded() -> None:
    refs = IssueRefs()
    evidence = {
        "issues": [
            {"id": A, "rule_id": "title_missing", "title": "Missing title"},
            {"id": B, "rule_id": "h1_missing", "title": "Missing H1"},
        ],
        "draft": {"issue_ids": [A]},
        "crawl": {"id": "not-an-issue"},
    }
    shown = refs.shorten(evidence)
    assert [i["id"] for i in shown["issues"]] == ["issue-a", "issue-b"]
    assert shown["draft"]["issue_ids"] == ["issue-a"]
    assert shown["crawl"]["id"] == "not-an-issue"  # only issues are renamed
    assert evidence["issues"][0]["id"] == A  # the original evidence is untouched

    answer = refs.expand(
        AgentAnswer(answer="Fix issue-b first, then Issue-A.", issue_ids=["issue-b", " ISSUE-A "])
    )
    assert answer.issue_ids == [B, A]
    assert answer.answer == "Fix “Missing H1” first, then “Missing title”."


def test_unknown_references_stay_unknown_for_grounding() -> None:
    refs = IssueRefs()
    refs.shorten({"id": A, "rule_id": "r", "title": "T"})
    answer = refs.expand(AgentAnswer(answer="x", issue_ids=["issue-z", B]))
    assert answer.issue_ids == ["issue-z", B]  # still rejected by the grounding check
    assert refs.expand_arguments({"issue_id": "issue-a", "limit": 5}) == {
        "issue_id": A,
        "limit": 5,
    }


def test_references_run_past_z_without_digits() -> None:
    refs = IssueRefs()
    shown = refs.shorten([{"id": f"id-{n}", "rule_id": "r"} for n in range(30)])
    assert shown[25]["id"] == "issue-z" and shown[26]["id"] == "issue-aa"
    assert not any(ch.isdigit() for item in shown for ch in item["id"])


def test_titles_never_push_text_past_its_limit() -> None:
    from app.modules.ai.outputs import KeyFinding, ManagementSummaryOutput, PriorityAction

    refs = IssueRefs()
    long_title = "Pages are missing a meta description, so search engines pick their own text"
    refs.shorten([{"id": A, "rule_id": "r", "title": long_title}])
    near_limit = ("Fix issue-a on the admissions pages. " * 11)[:398]
    summary = ManagementSummaryOutput(
        headline="Health summary",
        overview="The site needs a few metadata fixes.",
        key_findings=[KeyFinding(statement=near_limit, issue_ids=["issue-a"])],
        priorities=[PriorityAction(action="Fix issue-a", reason="See issue-a", issue_ids=[])],
    )
    expanded = refs.expand(summary)  # must not raise
    assert expanded.key_findings[0].issue_ids == [A]
    assert len(expanded.key_findings[0].statement) <= 400
    assert "issue A" in expanded.key_findings[0].statement
    # Short text still gets the readable title.
    assert expanded.priorities[0].action == f"Fix “{long_title}”"


def test_issues_named_in_the_text_are_cited() -> None:
    refs = IssueRefs()
    refs.shorten(
        [
            {"id": A, "rule_id": "title_missing", "title": "Page has no title"},
            {"id": B, "rule_id": "canonical", "title": "Canonical points elsewhere"},
        ]
    )
    # The model named issues only in its text, inside a bracket of references.
    answer = refs.expand(
        AgentAnswer(
            answer="Start with the pages without titles (issue-a, issue-b and issue-a), "
            "then fix issue-b.",
            issue_ids=[],
        )
    )
    assert answer.issue_ids == [A, B]
    assert answer.answer == (
        "Start with the pages without titles, then fix “Canonical points elsewhere”."
    )


def test_citations_from_the_text_respect_the_limit() -> None:
    refs = IssueRefs()
    issues = [{"id": f"00000000-0000-0000-0000-{n:012d}", "rule_id": "r"} for n in range(12)]
    shown = refs.shorten(issues)
    text = " ".join(i["id"] for i in shown)
    answer = refs.expand(AgentAnswer(answer=text, issue_ids=[]))
    assert len(answer.issue_ids) == 10  # AgentAnswer allows at most 10
