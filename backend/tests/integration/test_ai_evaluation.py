"""Measuring the AI: the usage report and the evaluation test set."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.cli import ai_eval, ai_report
from app.core.database import get_session_factory
from app.modules.ai.evaluation import EvalCase, load_cases, run_case, usage_report
from app.modules.ai.models import AIAnalysis, SeoRecommendation
from tests.fixtures.fake_ollama import FakeOllama
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed, enable_ai, run


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOllama]:
    from app.core.config import get_settings

    with FakeOllama(["llama3.1:latest", "other-model:latest"]) as fake:
        monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
        monkeypatch.setattr(get_settings(), "ollama_base_url", fake.base)
        monkeypatch.setattr(get_settings(), "ollama_default_model", "llama3.1")
        yield fake


async def _count(model: type) -> int:  # type: ignore[type-arg]
    async with get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


def test_the_starter_cases_are_valid() -> None:
    cases = load_cases()
    assert len(cases) >= 10
    assert {"question", "management_summary", "issue_explanation"} == {c.kind for c in cases}
    assert any(c.expect.admits_missing_data for c in cases)


def test_bad_cases_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate({"name": "q", "kind": "question"})  # no question
    with pytest.raises(ValidationError):
        EvalCase.model_validate({"name": "s", "kind": "management_summary", "question": "Why?"})
    with pytest.raises(ValidationError):
        EvalCase.model_validate({"name": "x", "kind": "metadata_draft"})  # has side effects
    with pytest.raises(ValidationError):
        EvalCase.model_validate(
            {"name": "x", "kind": "management_summary", "expect": {"made_up": True}}
        )
    with pytest.raises(ValidationError, match="contradict"):
        EvalCase.model_validate(
            {
                "name": "x",
                "kind": "question",
                "question": "Visitors?",
                "expect": {"answers": True, "admits_missing_data": True},
            }
        )
    twice = tmp_path / "cases.json"
    twice.write_text(json.dumps([{"name": "a", "kind": "management_summary"}] * 2))
    with pytest.raises(ValueError, match="unique name"):
        load_cases(twice)


async def test_cases_are_scored_and_leave_nothing_behind(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    import uuid

    factory, pid = get_session_factory(), uuid.UUID(project["id"])

    summary = await run_case(
        factory,
        pid,
        EvalCase(name="s", kind="management_summary", expect={"cites_top_issues": True}),
    )
    assert summary.passed and summary.completed and summary.grounded, summary.problems
    assert summary.attempts == 1 and summary.prompt_tokens and not summary.cold_start
    # The answer is kept for people to read, with cited issues by title.
    assert summary.output and summary.output["headline"] and summary.preview
    assert summary.cited_issues and all("(" in t for t in summary.cited_issues)

    explained = await run_case(factory, pid, EvalCase(name="e", kind="issue_explanation"))
    assert explained.passed, explained.problems

    # The fake model answers with an issue instead of admitting the data is missing.
    traffic = EvalCase(
        name="t",
        kind="question",
        question="How many visitors did we get?",
        expect={"admits_missing_data": True},
    )
    failed = await run_case(factory, pid, traffic)
    assert not failed.passed and failed.completed
    assert failed.problems == ["Does not start by saying that the platform has no data for this"]
    ollama.script({"action": "answer", "answer": "The platform does not have traffic data."})
    honest = await run_case(factory, pid, traffic)
    assert honest.passed, honest.problems
    # An admission buried after other material does not count.
    buried = "Fix the faculty page titles and the canonical tags first. " * 6
    ollama.script({"action": "answer", "answer": buried + "Traffic data is not available."})
    late = await run_case(factory, pid, traffic)
    assert late.problems == ["Does not start by saying that the platform has no data for this"]

    # A bare "no answer" fails where the project data does have one.
    ollama.script(
        {
            "action": "answer",
            "answer": "The project data does not contain an answer to this question.",
        }
    )
    refusal = await run_case(
        factory,
        pid,
        EvalCase(name="f", kind="question", question="Tell me about it.", expect={"answers": True}),
    )
    assert refusal.problems == ["Says the data has no answer, although the project data has one"]
    real = await run_case(
        factory,
        pid,
        EvalCase(name="f", kind="question", question="Tell me about it.", expect={"answers": True}),
    )
    assert real.passed, real.problems

    # When the site has none of the issues asked about, the answer must say so instead
    # of answering with other issues.
    rules = EvalCase(
        name="r",
        kind="question",
        question="Any hreflang problems?",
        expect={"cites_rules": ["no.such_rule"]},
    )
    off_topic = await run_case(factory, pid, rules)
    assert off_topic.problems == ["Does not say that the latest crawl found none of these issues"]
    ollama.script({"action": "answer", "answer": "The latest crawl found no hreflang problems."})
    none_found = await run_case(factory, pid, rules)
    assert none_found.passed, none_found.problems

    # Grounding still applies, and a different model can be tested.
    ollama.script(
        {"action": "answer", "answer": "You had 51234 visitors."},
        {"action": "answer", "answer": "You had 51234 visitors."},
    )
    invented = await run_case(
        factory,
        pid,
        EvalCase(name="i", kind="question", question="Visitors?"),
        model="other-model",
    )
    assert not invented.passed and not invented.grounded
    assert "Uses numbers that are not in the project data: 51234" in invented.problems
    assert ollama.requests[-1]["model"] == "other-model"

    assert await _count(AIAnalysis) == 0, "an evaluation must not store tasks"
    assert await _count(SeoRecommendation) == 0, "an evaluation must not store results"


async def test_eval_command_prints_and_saves_results(
    client: AsyncClient,
    site: FixtureSite,
    ollama: FakeOllama,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    out = tmp_path / "results.json"
    await ai_eval(org["slug"], project["name"].upper(), None, None, str(out))
    printed = capsys.readouterr().out
    assert "PASS  management-summary" in printed
    assert "FAIL  traffic-not-available" in printed  # the fake model does not admit it
    saved = json.loads(out.read_text())
    assert saved["project"] == project["name"] and saved["prompt_version"]
    assert saved["summary"]["cases"] == len(load_cases())
    assert saved["summary"]["completed"] == saved["summary"]["cases"]
    assert all(r["output"] for r in saved["results"])
    assert "      > " in printed  # an answer preview per case
    assert await _count(AIAnalysis) == 0

    with pytest.raises(SystemExit, match="No single project"):
        await ai_eval(org["slug"], "nowhere", None, None, None)


async def test_eval_refuses_a_project_that_was_never_analysed(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    from tests.integration.test_ai_api import setup

    owner, org, project = await setup(client, site)
    await enable_ai(client, owner, org["id"])
    with pytest.raises(SystemExit, match="has not been crawled and analysed yet"):
        await ai_eval(org["slug"], project["name"], None, None, None)
    # And a question that bypasses the queue's check still does not reach the model.
    import uuid

    result = await run_case(
        get_session_factory(),
        uuid.UUID(project["id"]),
        EvalCase(name="h", kind="question", question="Is the site healthy?"),
    )
    assert not result.completed and "Crawl and analyse" in result.problems[0]
    assert ollama.requests == []


async def test_report_counts_tasks_and_groups_failure_reasons(
    client: AsyncClient,
    site: FixtureSite,
    ollama: FakeOllama,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    assert (await run(client, owner, project["id"], kind="management_summary"))["status"] == (
        "completed"
    )
    ollama.script("not json", "still not json")
    await run(client, owner, project["id"], kind="management_summary")
    ollama.script(
        {"action": "answer", "answer": "You had 51234 visitors."},
        {"action": "answer", "answer": "You had 99871 visitors."},
    )
    await run(client, owner, project["id"], kind="question", question="Visitors?")

    import uuid

    async with get_session_factory()() as session:
        report = await usage_report(
            session, uuid.UUID(org["id"]), datetime.now(UTC) - timedelta(days=1)
        )
    by_kind = {k.kind: k for k in report.kinds}
    summary = by_kind["management_summary"]
    assert (summary.total, summary.completed, summary.failed) == (2, 1, 1)
    assert summary.avg_attempts == 1.5 and summary.avg_prompt_tokens and summary.cold_starts == 0
    reasons = dict(report.failure_reasons)
    assert reasons["The AI reply was not valid after 2 attempts"] == 1
    assert reasons["Uses numbers that are not in the project data"] == 1
    assert report.models == [("llama3.1", 3)]

    await ai_report(org["slug"], 30)
    printed = capsys.readouterr().out
    assert "management_summary" in printed and "Most common failure reasons" in printed
    await ai_report(org["slug"], 1)
    with pytest.raises(SystemExit, match="No organisation"):
        await ai_report("missing", 30)


def test_honest_replies_about_missing_data_are_recognised() -> None:
    from app.modules.ai.evaluation import _MISSING_DATA

    for honest in (
        "The data does not provide information on which competitors rank above us.",
        "Visitor numbers are not available in the project data.",
        "This platform doesn't record traffic.",
        "Rankings are not tracked by this platform.",
        "There is no information about competitors.",
    ):
        assert _MISSING_DATA.search(honest), honest
    assert not _MISSING_DATA.search("Fix the missing titles on the faculty pages first.")


def test_organisation_test_sets_are_valid() -> None:
    files = sorted((Path(__file__).parents[2] / "evals").glob("*.json"))
    assert files, "the evals folder should hold organisation test sets"
    for path in files:
        assert load_cases(path), path


async def test_feedback_is_given_reported_and_exported(
    client: AsyncClient,
    site: FixtureSite,
    ollama: FakeOllama,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.cli import ai_feedback_cases
    from tests.conftest import add_member, make_user

    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    viewer = await make_user(client, "viewer@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    pid = project["id"]

    asked = await run(client, owner, pid, kind="question", question="Is the site slow?")
    url = f"/api/v1/ai-analyses/{asked['id']}/feedback"
    assert asked["my_feedback"] is None
    bad = await client.put(
        url,
        json={"rating": "not_helpful", "reason": "off_topic", "comment": "Talked about titles"},
        headers=owner.headers,
    )
    assert bad.status_code == 200 and bad.json()["reason"] == "off_topic"
    # One verdict per person: giving it again replaces it, and a helpful one drops the reason.
    changed = await client.put(
        url, json={"rating": "helpful", "reason": "vague"}, headers=owner.headers
    )
    assert changed.json() == {**changed.json(), "rating": "helpful", "reason": None}
    await client.put(
        url,
        json={"rating": "not_helpful", "reason": "off_topic", "comment": " Off topic "},
        headers=owner.headers,
    )
    # Viewers may give feedback too, and each person sees their own.
    seen = await client.put(url, json={"rating": "helpful"}, headers=viewer.headers)
    assert seen.status_code == 200
    mine = (await client.get(f"/api/v1/ai-analyses/{asked['id']}", headers=owner.headers)).json()
    assert mine["my_feedback"]["rating"] == "not_helpful"
    assert mine["my_feedback"]["comment"] == "Off topic"
    theirs = (await client.get(f"/api/v1/ai-analyses/{asked['id']}", headers=viewer.headers)).json()
    assert theirs["my_feedback"]["rating"] == "helpful"

    invalid = await client.put(url, json={"rating": "meh"}, headers=owner.headers)
    assert invalid.status_code == 422

    page_q = await run(client, owner, pid, kind="question", question="What is wrong with /about?")
    await client.put(
        f"/api/v1/ai-analyses/{page_q['id']}/feedback",
        json={"rating": "not_helpful", "reason": "wrong"},
        headers=owner.headers,
    )

    import uuid

    async with get_session_factory()() as session:
        report = await usage_report(
            session, uuid.UUID(org["id"]), datetime.now(UTC) - timedelta(days=1)
        )
    fb = report.feedback
    assert (fb.helpful, fb.not_helpful) == (1, 2)
    assert dict(fb.reasons) == {"off_topic": 1, "wrong": 1}
    assert ("question", "Is the site slow?", "off_topic", "Off topic") in fb.recent_complaints

    out = tmp_path / "feedback.json"
    await ai_feedback_cases(org["slug"], 30, str(out))
    cases = load_cases(out)
    by_question = {c.question: c for c in cases}
    assert by_question["Is the site slow?"].expect.cites_rules == ["tech.slow_response"]
    assert by_question["What is wrong with /about?"].expect.cites_page_issues
    assert "Wrote 2 test cases" in capsys.readouterr().out

    # The exported cases run as they are.
    result = await run_case(
        get_session_factory(), uuid.UUID(pid), by_question["What is wrong with /about?"]
    )
    assert result.completed


async def test_queued_tasks_take_no_feedback(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    queued = await client.post(
        f"/api/v1/projects/{project['id']}/ai/analyses",
        json={"kind": "management_summary"},
        headers=owner.headers,
    )
    response = await client.put(
        f"/api/v1/ai-analyses/{queued.json()['id']}/feedback",
        json={"rating": "helpful"},
        headers=owner.headers,
    )
    assert response.status_code == 409
