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
    assert failed.problems == ["Does not say that the platform has no data for this"]
    ollama.script({"action": "answer", "answer": "The platform does not have traffic data."})
    honest = await run_case(factory, pid, traffic)
    assert honest.passed, honest.problems

    # A rule the site has no open issue for is skipped, not failed.
    rules = EvalCase(
        name="r",
        kind="question",
        question="Any hreflang problems?",
        expect={"cites_rules": ["no.such_rule"]},
    )
    skipped = await run_case(factory, pid, rules)
    assert skipped.passed and skipped.skipped_checks

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
    assert await _count(AIAnalysis) == 0

    with pytest.raises(SystemExit, match="No single project"):
        await ai_eval(org["slug"], "nowhere", None, None, None)


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
