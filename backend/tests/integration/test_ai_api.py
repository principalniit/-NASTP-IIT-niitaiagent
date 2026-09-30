"""The AI layer through the API and the worker, with a local fake Ollama server."""

import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.worker import process_next_ai_task, process_next_analysis, process_next_job
from tests.conftest import TestUser, add_member, make_user
from tests.fixtures.fake_ollama import FakeOllama
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_crawl_api import engine_for, setup

UNGROUNDED = {
    "headline": "Big wins ahead",
    "overview": "Fixing these issues guarantees a top position and 500 more visitors.",
    "key_findings": [{"statement": "Traffic will increase quickly.", "issue_ids": []}],
    "priorities": [{"action": "Fix titles", "reason": "It affects 77 pages."}],
}
BAD_METADATA = {
    "title": "Be the top result on Google",
    "meta_description": "Guaranteed admission for every applicant.",
    "rationale": "Makes the page more attractive.",
}


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOllama]:
    with FakeOllama(["llama3.1:latest"]) as fake:
        monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
        monkeypatch.setattr(get_settings(), "ollama_base_url", fake.base)
        monkeypatch.setattr(get_settings(), "ollama_default_model", "llama3.1")
        yield fake


async def enable_ai(client: AsyncClient, owner: TestUser, org_id: str) -> None:
    response = await client.patch(
        f"/api/v1/organisations/{org_id}",
        json={"settings": {"ai": {"provider": "ollama"}}},
        headers=owner.headers,
    )
    assert response.status_code == 200, response.text


async def analysed(client: AsyncClient, site: FixtureSite):  # type: ignore[no-untyped-def]
    owner, org, project = await setup(client, site)
    await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    await process_next_job("w", engine_factory=engine_for(site))
    assert await process_next_analysis()
    return owner, org, project


async def run(client: AsyncClient, user: TestUser, project_id: str, **body: object) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"/api/v1/projects/{project_id}/ai/analyses", json=body, headers=user.headers
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    assert await process_next_ai_task()
    result = await client.get(f"/api/v1/ai-analyses/{response.json()['id']}", headers=user.headers)
    return result.json()  # type: ignore[no-any-return]


async def test_ai_is_off_by_default(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await analysed(client, site)
    status = (
        await client.get(f"/api/v1/organisations/{org['id']}/ai/status", headers=owner.headers)
    ).json()
    assert status["enabled"] is False and status["status"] == "disabled"
    response = await client.post(
        f"/api/v1/projects/{project['id']}/ai/analyses",
        json={"kind": "management_summary"},
        headers=owner.headers,
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "ai_disabled"
    # The deterministic engine is unaffected.
    issues = await client.get(f"/api/v1/projects/{project['id']}/issues", headers=owner.headers)
    assert issues.json()["total"] > 0
    assert not await process_next_ai_task()


async def test_ai_tasks_produce_grounded_results_and_drafts(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    pid, h = project["id"], owner.headers
    await enable_ai(client, owner, org["id"])
    status = (await client.get(f"/api/v1/organisations/{org['id']}/ai/status", headers=h)).json()
    assert status == {
        "enabled": True,
        "provider": "ollama",
        "model": "llama3.1",
        "status": "available",
        "detail": "llama3.1",
    }

    summary = await run(client, owner, pid, kind="management_summary")
    assert summary["status"] == "completed", summary["error"]
    assert summary["grounding"]["passed"] and summary["attempts"] == 1
    assert summary["prompt_version"] and summary["model"] == "llama3.1"
    assert summary["evidence"]["project_summary"]["latest_analysed_crawl"]
    known = {i["id"] for i in summary["evidence"]["top_open_issues"]["issues"]}
    assert {i for f in summary["output"]["key_findings"] for i in f["issue_ids"]} <= known
    prompt = ollama.requests[-1]["messages"]
    assert "Never invent" in prompt[0]["content"] and "EVIDENCE (JSON)" in prompt[1]["content"]

    issue = (await client.get(f"/api/v1/projects/{pid}/issues", headers=h)).json()["items"][0]
    explained = await run(client, owner, pid, kind="issue_explanation", issue_id=issue["id"])
    assert explained["status"] == "completed" and explained["subject_id"] == issue["id"]
    recs = (await client.get(f"/api/v1/projects/{pid}/recommendations", headers=h)).json()
    assert recs["total"] == 1 and recs["items"][0]["issue_ids"] == [issue["id"]]
    # The model saw a short reference, not the long id it could mistype.
    sent = ollama.requests[-1]["messages"][1]["content"]
    assert '"issue-a"' in sent and issue["id"] not in sent
    accepted = await client.patch(
        f"/api/v1/recommendations/{recs['items'][0]['id']}", json={"status": "accepted"}, headers=h
    )
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"

    plan = await run(client, owner, pid, kind="page_plan", page_url="/about")
    assert plan["status"] == "completed"
    assert (await client.get(f"/api/v1/projects/{pid}/recommendations", headers=h)).json()[
        "total"
    ] == 1 + len(plan["output"]["improvements"])

    metadata = await run(client, owner, pid, kind="metadata_draft", page_url="/about")
    assert metadata["status"] == "completed" and len(metadata["draft_ids"]) == 2
    drafts = (await client.get(f"/api/v1/projects/{pid}/drafts", headers=h)).json()["items"]
    fields = {d["field"]: d for d in drafts}
    assert set(fields) == {"title", "meta_description"}
    title = fields["title"]
    assert title["source"] == "ai" and title["status"] == "draft" and title["version"] == 1
    assert title["original_content"] == "About" and title["page_url"].endswith("/about")
    assert title["ai_analysis_id"] == metadata["id"] and title["created_by_id"] is None

    outline = await run(
        client, owner, pid, kind="content_outline", page_url="/about", goal="Clarity"
    )
    assert outline["status"] == "completed" and len(outline["draft_ids"]) == 1
    detail = (await client.get(f"/api/v1/drafts/{outline['draft_ids'][0]}", headers=h)).json()
    assert detail["field"] == "content_outline" and "[verify:" in detail["proposed_content"]
    assert "Editor's goal: Clarity" in ollama.requests[-1]["messages"][1]["content"]

    answer = await run(client, owner, pid, kind="question", question="What should we fix first?")
    assert answer["status"] == "completed", answer["error"]
    assert answer["output"]["tools_used"] == ["get_seo_issues"]
    assert answer["output"]["issue_ids"] and answer["grounding"]["passed"]

    listing = (await client.get(f"/api/v1/projects/{pid}/ai/analyses", headers=h)).json()
    assert listing["total"] == 6
    only = await client.get(
        f"/api/v1/projects/{pid}/ai/analyses", params={"kind": "question"}, headers=h
    )
    assert only.json()["total"] == 1
    by_issue = await client.get(
        f"/api/v1/projects/{pid}/ai/analyses", params={"subject_id": issue["id"]}, headers=h
    )
    assert [a["id"] for a in by_issue.json()["items"]] == [explained["id"]]
    about = title["page_url"]
    by_page = await client.get(
        f"/api/v1/projects/{pid}/ai/analyses", params={"page_url": about}, headers=h
    )
    assert {a["kind"] for a in by_page.json()["items"]} == {
        "page_plan",
        "metadata_draft",
        "content_outline",
    }
    page_drafts = await client.get(
        f"/api/v1/projects/{pid}/drafts", params={"page_url": about}, headers=h
    )
    assert page_drafts.json()["total"] == 3
    other_page = await client.get(
        f"/api/v1/projects/{pid}/drafts", params={"page_url": about + "-copy"}, headers=h
    )
    assert other_page.json()["total"] == 0
    audit = (await client.get(f"/api/v1/organisations/{org['id']}/audit-logs", headers=h)).json()
    assert "ai.requested" in {e["action"] for e in audit["items"]}


async def test_ungrounded_reply_is_retried_then_rejected(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])

    ollama.script(UNGROUNDED)  # the retry falls back to a grounded auto reply
    recovered = await run(client, owner, project["id"], kind="management_summary")
    assert recovered["status"] == "completed" and recovered["attempts"] == 2
    assert "not grounded in the evidence" in ollama.requests[-1]["messages"][-1]["content"]

    ollama.script(UNGROUNDED, UNGROUNDED)
    rejected = await run(client, owner, project["id"], kind="management_summary")
    assert rejected["status"] == "failed" and rejected["output"] is None  # never shown
    assert rejected["error"] == (
        "The AI reply included claims not supported by the project data, so it was not used."
    )
    violations = " ".join(rejected["grounding"]["violations"])
    assert "500" in violations and "77" in violations and "unsupported claim" in violations

    ollama.script(BAD_METADATA, BAD_METADATA)
    no_drafts = await run(client, owner, project["id"], kind="metadata_draft", page_url="/about")
    assert no_drafts["status"] == "failed" and no_drafts["draft_ids"] == []
    drafts = await client.get(f"/api/v1/projects/{project['id']}/drafts", headers=owner.headers)
    assert drafts.json()["total"] == 0


async def test_ai_failures_are_reported_not_raised(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])

    ollama.script("not json", "still not json")
    invalid = await run(client, owner, project["id"], kind="management_summary")
    assert invalid["status"] == "failed" and "not valid after 2 attempts" in invalid["error"]

    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")
    down = await run(client, owner, project["id"], kind="management_summary")
    assert (
        down["status"] == "failed" and down["error"] == "The AI service (Ollama) is not reachable."
    )
    status = (
        await client.get(f"/api/v1/organisations/{org['id']}/ai/status", headers=owner.headers)
    ).json()
    assert status["enabled"] and status["status"] == "unavailable"

    # Switching AI off after a request was queued fails the task instead of running it.
    monkeypatch.setattr(get_settings(), "ollama_base_url", ollama.base)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/ai/analyses",
        json={"kind": "management_summary"},
        headers=owner.headers,
    )
    monkeypatch.setattr(get_settings(), "ai_provider", "none")
    assert await process_next_ai_task()
    off = (
        await client.get(f"/api/v1/ai-analyses/{response.json()['id']}", headers=owner.headers)
    ).json()
    assert off["status"] == "failed" and off["error"] == "AI is disabled on this platform."


async def test_request_validation_permissions_and_limits(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    url = f"/api/v1/projects/{project['id']}/ai/analyses"
    h = owner.headers

    for body in (
        {"kind": "issue_explanation"},
        {"kind": "metadata_draft"},
        {"kind": "question"},
        {"kind": "question", "question": "hi"},
        {"kind": "management_summary", "unexpected": 1},
    ):
        assert (await client.post(url, json=body, headers=h)).status_code == 422, body
    missing_issue = {
        "kind": "issue_explanation",
        "issue_id": "11111111-2222-3333-4444-555555555555",
    }
    assert (await client.post(url, json=missing_issue, headers=h)).status_code == 404
    for page in ("/not-crawled", "/file.pdf", "https://external.example.com/"):
        body = {"kind": "metadata_draft", "page_url": page}
        assert (await client.post(url, json=body, headers=h)).status_code == 404, page

    viewer = await make_user(client, "viewer@example.org")
    editor = await make_user(client, "editor@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    await add_member(client, owner, org["id"], editor, "editor")
    summary = {"kind": "management_summary"}
    assert (await client.post(url, json=summary, headers=viewer.headers)).status_code == 403
    assert (await client.post(url, json=summary, headers=editor.headers)).status_code == 403
    draft_request = {"kind": "metadata_draft", "page_url": "/about"}
    assert (await client.post(url, json=draft_request, headers=viewer.headers)).status_code == 403
    assert (await client.post(url, json=draft_request, headers=editor.headers)).status_code == 202
    assert (await client.get(url, headers=viewer.headers)).status_code == 200

    monkeypatch.setattr(get_settings(), "ai_max_active_jobs_per_org", 2)
    assert (await client.post(url, json=summary, headers=h)).status_code == 202
    assert (await client.post(url, json=summary, headers=h)).status_code == 429


async def test_ai_needs_an_analysed_crawl(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await setup(client, site)
    await enable_ai(client, owner, org["id"])
    response = await client.post(
        f"/api/v1/projects/{project['id']}/ai/analyses",
        json={"kind": "management_summary"},
        headers=owner.headers,
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_analysed"


async def test_compare_crawls(client: AsyncClient, site: FixtureSite) -> None:
    owner, _, project = await analysed(client, site)
    url = f"/api/v1/projects/{project['id']}/compare"
    single = await client.get(url, headers=owner.headers)
    assert single.status_code == 400 and single.json()["error"]["code"] == "not_enough_crawls"

    site.page("/about", "About NIIT and its programmes", "<h1>About</h1><p>Changed text</p>")
    site.page("/missing", "Found again", "<h1>Found</h1><p>Now it exists</p><a href='/'>Home</a>")
    await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    await process_next_job("w", engine_factory=engine_for(site))
    assert await process_next_analysis()

    result = (await client.get(url, headers=owner.headers)).json()
    pages = result["pages"]
    assert any(
        c["url"].endswith("/missing") and c["to"] == 200 for c in pages["status_changes"]["items"]
    )
    assert any(c["url"].endswith("/about") for c in pages["title_changes"]["items"])
    assert any(u.endswith("/about") for u in pages["content_changed"]["items"])
    resolved = {i["rule_id"] for i in result["issues"]["resolved"]["items"]}
    assert "tech.http_client_error" in resolved
    assert result["score_change"]["overall"]["from"] is not None
    bogus = await client.get(
        url, params={"from_crawl": "11111111-2222-3333-4444-555555555555"}, headers=owner.headers
    )
    assert bogus.status_code == 404


async def test_agent_tool_loop_is_bounded_and_allow_listed(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])

    def call(tool: str, **arguments: object) -> dict:  # type: ignore[type-arg]
        return {"action": "call_tool", "tool": tool, "arguments": arguments}

    ollama.script(
        call("run_sql", query="select * from users"),
        call("get_page_details", url="/about", extra="x"),
        call("get_crawl_status"),
        call("get_crawl_status"),
        call("get_crawl_status"),  # over the limit: the model is told to answer
        {"action": "answer", "answer": "The latest crawl has finished."},
    )
    result = await run(client, owner, project["id"], kind="question", question="Is the crawl done?")
    assert result["status"] == "completed", result["error"]
    assert result["output"]["answer"] == "The latest crawl has finished."
    tools = result["evidence"]["tool_results"]
    assert [t["tool"] for t in tools] == [
        "run_sql",
        "get_page_details",
        "get_crawl_status",
        "get_crawl_status",
    ]
    assert tools[0]["result"]["error"].startswith("Unknown tool 'run_sql'")
    assert "error" in tools[1]["result"]
    last = ollama.requests[-1]["messages"][-1]["content"]
    assert last == "No more tool calls are allowed. Answer now with the evidence you have."

    ollama.script(*[call("get_crawl_status")] * 8)
    stuck = await run(client, owner, project["id"], kind="question", question="Loop forever?")
    assert stuck["status"] == "failed" and "allowed number of steps" in stuck["error"]


async def test_ai_drafts_follow_the_approval_workflow(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    manager = await make_user(client, "manager@example.org")
    await add_member(client, owner, org["id"], manager, "seo_manager")
    result = await run(client, owner, project["id"], kind="metadata_draft", page_url="/about")
    did = result["draft_ids"][0]
    submit = await client.post(f"/api/v1/drafts/{did}/submit", json={}, headers=owner.headers)
    assert submit.status_code == 200
    own = await client.post(f"/api/v1/drafts/{did}/approve", json={}, headers=owner.headers)
    assert own.status_code == 403  # whoever submits an AI draft cannot also approve it
    approved = await client.post(f"/api/v1/drafts/{did}/approve", json={}, headers=manager.headers)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    trail = (await client.get(f"/api/v1/drafts/{did}", headers=owner.headers)).json()["trail"]
    assert trail[0]["action"] == "created" and trail[0]["actor_id"] is None
    assert trail[0]["comment"] == "Generated by the AI assistant"


async def test_worker_contains_crashes_and_recovers_stale_tasks(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.worker as worker
    from app.core.database import get_session_factory
    from app.modules.ai.models import AIAnalysis, AIStatus

    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    url = f"/api/v1/projects/{project['id']}/ai/analyses"

    async def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(worker, "run_analysis", crash)
    queued = (
        await client.post(url, json={"kind": "management_summary"}, headers=owner.headers)
    ).json()
    assert await process_next_ai_task()
    crashed = (
        await client.get(f"/api/v1/ai-analyses/{queued['id']}", headers=owner.headers)
    ).json()
    assert crashed["status"] == "failed" and "secret" not in crashed["error"]
    assert crashed["finished_at"]

    stuck = (
        await client.post(url, json={"kind": "management_summary"}, headers=owner.headers)
    ).json()
    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(AIAnalysis, uuid.UUID(stuck["id"]))
        assert row is not None
        row.status = AIStatus.RUNNING
        row.started_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()
    await worker.recover_stale_jobs(factory, 300)
    recovered = (
        await client.get(f"/api/v1/ai-analyses/{stuck['id']}", headers=owner.headers)
    ).json()
    assert recovered["status"] == "failed" and "stopped unexpectedly" in recovered["error"]


async def test_a_model_citing_references_in_prose_gets_titles_and_real_ids(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    """How local models actually reply: short references in sentences and in issue_ids,
    sometimes in capitals. The stored summary has real ids and readable titles."""

    def reply(request: dict[str, Any]) -> dict[str, Any]:
        refs = sorted(set(re.findall(r"issue-[a-z]+", request["messages"][1]["content"])))[:3]
        return {
            "headline": "The site has several metadata and heading gaps",
            "overview": f"Most pages load, but {refs[0]} and {refs[1]} affect many pages.",
            "key_findings": [
                {"statement": f"{r} needs attention across the site.", "issue_ids": [r]}
                for r in refs
            ],
            "priorities": [
                {
                    "action": f"Fix {refs[0]}",
                    "reason": f"{refs[0]} has the highest priority.",
                    "issue_ids": [refs[0].upper()],
                }
            ],
            "data_limitations": ["Only one crawl has been analysed."],
        }

    owner, org, project = await analysed(client, site)
    await enable_ai(client, owner, org["id"])
    ollama.script(reply)
    result = await run(client, owner, project["id"], kind="management_summary")
    assert result["status"] == "completed", result["error"]
    output = result["output"]
    known = {
        i["id"]
        for i in (
            await client.get(
                f"/api/v1/projects/{project['id']}/issues",
                params={"page_size": 100},
                headers=owner.headers,
            )
        ).json()["items"]
    }
    cited = {i for f in output["key_findings"] for i in f["issue_ids"]}
    cited |= set(output["priorities"][0]["issue_ids"])
    assert cited and cited <= known  # real ids, including the one written in capitals
    assert "issue-" not in json.dumps(output).lower()  # prose shows titles, not references
    assert output["key_findings"][0]["statement"].startswith("“")


async def test_summary_after_two_crawls_is_stored(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    """With two analysed crawls the evidence includes the crawl comparison, whose dates
    must be stored as plain JSON (this failed as an internal error before)."""
    owner, org, project = await analysed(client, site)
    await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    await process_next_job("w", engine_factory=engine_for(site))
    assert await process_next_analysis()
    await enable_ai(client, owner, org["id"])
    result = await run(client, owner, project["id"], kind="management_summary")
    assert result["status"] == "completed", result["error"]
    comparison = result["evidence"]["comparison"]
    assert isinstance(comparison["to_crawl"]["finished_at"], str)
