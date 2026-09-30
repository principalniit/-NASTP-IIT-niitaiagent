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
