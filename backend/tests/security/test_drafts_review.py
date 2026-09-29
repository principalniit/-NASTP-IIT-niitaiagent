"""Findings from the Phase 6 security review: approvals, protected facts, AI grounding."""

import uuid
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.modules.ai.agent import _grounding_facts
from app.modules.ai.grounding import numbers_in
from app.modules.ai.tasks import issue_ids_in
from app.modules.crawler.models import CrawlPage
from app.modules.projects.models import ProjectSettings
from tests.conftest import add_member, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed
from tests.integration.test_drafts_api import act, create, team

FACT = "Admissions close 15 March 2027"


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def test_a_typed_original_cannot_hide_new_facts(
    client: AsyncClient, site: FixtureSite
) -> None:
    owner, org, project = await analysed(client, site)
    editor = await make_user(client, "editor@example.org")
    await add_member(client, owner, org["id"], editor, "editor")
    async with get_session_factory()() as session:
        page = await session.scalar(
            select(CrawlPage).where(CrawlPage.title.is_not(None)).order_by(CrawlPage.url)
        )
        assert page is not None
        url, crawled_title = page.url, page.title
    # The author claims the page already says the new fact.
    made = await create(
        client,
        editor,
        project["id"],
        page_url=url,
        original_content=FACT,
        proposed_content=FACT,
    )
    draft = made.json()
    assert made.status_code == 201, made.text
    assert draft["original_content"] == crawled_title  # the crawled value, not the typed one
    assert draft["protected"] is True

    # For a page or field with no crawled value, typed text is kept for reference only.
    section = await create(
        client,
        editor,
        project["id"],
        page_url="/not-crawled",
        field="content_section",
        original_content=FACT,
        proposed_content=FACT,
    )
    assert section.json()["original_content"] == FACT and section.json()["protected"] is True


async def test_nobody_who_wrote_or_submitted_a_draft_approves_it(client: AsyncClient) -> None:
    _, project, p = await team(client)
    manager, editor, owner = p["seo_manager"], p["editor"], p["owner"]
    did = (await create(client, manager, project["id"])).json()["id"]
    unchanged = await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "Admissions | How to apply to NIIT", "reason": "No change"},
        headers=editor.headers,
    )
    assert unchanged.status_code == 409  # a no-op edit cannot launder authorship
    await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "Admissions | How to apply to NIIT.", "reason": "Full stop"},
        headers=editor.headers,
    )
    await act(client, editor, did, "submit")
    assert (await act(client, manager, did, "approve")).status_code == 403  # wrote version 1
    detail = (await client.get(f"/api/v1/drafts/{did}", headers=owner.headers)).json()
    assert set(detail["contributor_ids"]) == {manager.id, editor.id}  # shown to the dashboard

    # An earlier submitter of the same version stays barred after a reject and reopen.
    did2 = (await create(client, editor, project["id"])).json()["id"]
    await act(client, manager, did2, "submit")
    await act(client, owner, did2, "reject", comment="Needs the full name")
    await act(client, editor, did2, "reopen")
    await act(client, editor, did2, "submit")
    assert (await act(client, manager, did2, "approve")).status_code == 403
    assert (await act(client, owner, did2, "approve")).status_code == 200


async def test_source_addresses_must_be_on_an_approved_source(client: AsyncClient) -> None:
    _, project, p = await team(client)
    async with get_session_factory()() as session:
        row = await session.get(ProjectSettings, uuid.UUID(project["id"]))
        assert row is not None
        row.settings = {
            **row.settings,
            "institutional_profile": {
                "approved_sources": [
                    {"label": "Admissions office", "url": "https://example.org/admissions"}
                ]
            },
        }
        await session.commit()

    async def pending() -> str:
        made = await create(
            client, p["editor"], project["id"], field="meta_description", proposed_content=FACT
        )
        await act(client, p["editor"], made.json()["id"], "submit")
        return str(made.json()["id"])

    for bad in (
        "https://evil.example/admissions",
        "https://example.org/admissions-fake",
        "http://example.org/admissions/2027",
        "www.example.org/admissions",
    ):
        refused = await act(
            client, p["seo_manager"], await pending(), "approve", source_reference=bad
        )
        assert refused.status_code == 409, bad
    for good in (
        "https://example.org/admissions/notice-2027",
        "Admissions office notice AO-2027-03",
    ):
        ok = await act(client, p["seo_manager"], await pending(), "approve", source_reference=good)
        assert ok.status_code == 200, good


def test_answers_are_grounded_on_tool_results_not_tool_arguments() -> None:
    planted = "11111111-2222-3333-4444-555555555555"
    evidence = {
        "project_summary": {"pages": 12},
        "tool_results": [
            {"tool": "bogus", "arguments": {"id": planted, "n": "48213"}, "result": {"error": "x"}},
            {"tool": "get_issue", "arguments": {"n": "777"}, "result": {"title": "Missing"}},
        ],
    }
    facts = _grounding_facts(evidence)
    assert planted not in issue_ids_in(facts)
    assert "48213" not in numbers_in(facts) and "777" not in numbers_in(facts)
    assert "12" in numbers_in(facts)
