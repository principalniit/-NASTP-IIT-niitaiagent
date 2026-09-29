"""AI analyses, recommendations, drafts and AI tools never cross organisation boundaries."""

import uuid
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.core.database import get_session_factory
from app.modules.ai.tools import (
    IssueArgs,
    PageArgs,
    ToolContext,
    ToolError,
    get_issue_evidence,
    get_page_details,
)
from app.modules.projects.models import Project
from tests.conftest import add_member, make_org, make_project, make_user
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

    with FakeOllama(["llama3.1:latest"]) as fake:
        monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
        monkeypatch.setattr(get_settings(), "ollama_base_url", fake.base)
        monkeypatch.setattr(get_settings(), "ollama_default_model", "llama3.1")
        yield fake


async def test_ai_and_draft_resources_are_isolated(
    client: AsyncClient, site: FixtureSite, ollama: FakeOllama
) -> None:
    owner_b, org_b, project_b = await analysed(client, site)
    await enable_ai(client, owner_b, org_b["id"])
    pid_b = project_b["id"]
    issue_b = (
        await client.get(f"/api/v1/projects/{pid_b}/issues", headers=owner_b.headers)
    ).json()["items"][0]
    explained = await run(client, owner_b, pid_b, kind="issue_explanation", issue_id=issue_b["id"])
    drafted = await run(client, owner_b, pid_b, kind="metadata_draft", page_url="/about")
    rec_b = (
        await client.get(f"/api/v1/projects/{pid_b}/recommendations", headers=owner_b.headers)
    ).json()["items"][0]
    draft_b = drafted["draft_ids"][0]

    alice = await make_user(client, "alice@example.org")
    org_a = await make_org(client, owner_b, "Org A")
    await add_member(client, owner_b, org_a["id"], alice, "owner")
    project_a = await make_project(client, alice, org_a["id"], "https://a.example.org")
    await enable_ai(client, alice, org_a["id"])
    h = alice.headers
    for method, path, body in (
        ("GET", f"/api/v1/organisations/{org_b['id']}/ai/status", None),
        ("GET", f"/api/v1/projects/{pid_b}/ai/analyses", None),
        ("POST", f"/api/v1/projects/{pid_b}/ai/analyses", {"kind": "management_summary"}),
        ("GET", f"/api/v1/ai-analyses/{explained['id']}", None),
        ("GET", f"/api/v1/projects/{pid_b}/recommendations", None),
        ("PATCH", f"/api/v1/recommendations/{rec_b['id']}", {"status": "dismissed"}),
        ("GET", f"/api/v1/projects/{pid_b}/compare", None),
        ("GET", f"/api/v1/projects/{pid_b}/drafts", None),
        (
            "POST",
            f"/api/v1/projects/{pid_b}/drafts",
            {
                "page_url": "https://x.org/",
                "field": "title",
                "proposed_content": "x",
                "reason": "Test reason",
            },
        ),
        ("GET", f"/api/v1/drafts/{draft_b}", None),
        ("PATCH", f"/api/v1/drafts/{draft_b}", {"proposed_content": "x", "reason": "Takeover"}),
        ("POST", f"/api/v1/drafts/{draft_b}/submit", {}),
        ("POST", f"/api/v1/drafts/{draft_b}/approve", {}),
        ("POST", f"/api/v1/drafts/{draft_b}/reject", {"comment": "No thanks"}),
        ("POST", f"/api/v1/drafts/{draft_b}/mark-published", {}),
    ):
        response = await client.request(method, path, json=body, headers=h)
        assert response.status_code == 404, (method, path, response.status_code)

    # Alice cannot point her own project's AI at Org B's issue.
    foreign = await client.post(
        f"/api/v1/projects/{project_a['id']}/ai/analyses",
        json={"kind": "issue_explanation", "issue_id": issue_b["id"]},
        headers=h,
    )
    assert foreign.status_code in (404, 409)
    # Org B's data is unchanged.
    rec = (
        await client.get(f"/api/v1/projects/{pid_b}/recommendations", headers=owner_b.headers)
    ).json()["items"][0]
    assert rec["status"] == "open"
    draft = (await client.get(f"/api/v1/drafts/{draft_b}", headers=owner_b.headers)).json()
    assert draft["status"] == "draft" and draft["version"] == 1


async def test_ai_tools_are_scoped_to_one_project(client: AsyncClient, site: FixtureSite) -> None:
    owner_b, _, project_b = await analysed(client, site)
    issue_b = (
        await client.get(f"/api/v1/projects/{project_b['id']}/issues", headers=owner_b.headers)
    ).json()["items"][0]
    org_a = await make_org(client, owner_b, "Org A")
    project_a = await make_project(client, owner_b, org_a["id"], "https://a.example.org")
    async with get_session_factory()() as session:
        own = await session.get(Project, uuid.UUID(project_a["id"]))
        assert own is not None
        tools = ToolContext(session, own)
        with pytest.raises(ToolError):
            await get_issue_evidence(tools, IssueArgs(issue_id=uuid.UUID(issue_b["id"])))
        with pytest.raises(ToolError):
            await get_page_details(tools, PageArgs(url=f"{site.base}/about"))

        other = await session.get(Project, uuid.UUID(project_b["id"]))
        assert other is not None
        scoped = ToolContext(session, other)
        assert (await get_issue_evidence(scoped, IssueArgs(issue_id=uuid.UUID(issue_b["id"]))))[
            "id"
        ] == issue_b["id"]
