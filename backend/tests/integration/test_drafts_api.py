"""Content drafts and the approval workflow. Nothing here publishes anything."""

from httpx import AsyncClient

from tests.conftest import TestUser, add_member, make_org, make_project, make_user

PAGE = "https://example.org/admissions"


async def team(client: AsyncClient):  # type: ignore[no-untyped-def]
    owner = await make_user(client, "owner@example.org", platform_admin=True, name="Olivia Owner")
    org = await make_org(client, owner, "Org")
    project = await make_project(client, owner, org["id"])
    people = {"owner": owner}
    for role in ("seo_manager", "editor", "viewer"):
        user = await make_user(client, f"{role}@example.org", name=role.replace("_", " ").title())
        await add_member(client, owner, org["id"], user, role)
        people[role] = user
    return org, project, people


async def create(client: AsyncClient, user: TestUser, project_id: str, **overrides: object):  # type: ignore[no-untyped-def]
    body = {
        "page_url": PAGE,
        "field": "title",
        "original_content": "Admissions",
        "proposed_content": "Admissions | How to apply to NIIT",
        "reason": "The current title is too short to describe the page.",
    } | overrides
    return await client.post(
        f"/api/v1/projects/{project_id}/drafts", json=body, headers=user.headers
    )


async def act(client: AsyncClient, user: TestUser, draft_id: str, action: str, **body: object):  # type: ignore[no-untyped-def]
    return await client.post(f"/api/v1/drafts/{draft_id}/{action}", json=body, headers=user.headers)


async def test_full_lifecycle_with_versions_and_trail(client: AsyncClient) -> None:
    org, project, p = await team(client)
    editor, manager = p["editor"], p["seo_manager"]

    created = await create(client, editor, project["id"])
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft" and draft["version"] == 1 and draft["source"] == "human"
    assert draft["protected"] is False and draft["created_by_id"] == editor.id
    did = draft["id"]

    edited = await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "Admissions | Apply to NIIT", "reason": "Shorter wording."},
        headers=editor.headers,
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2

    assert (await act(client, editor, did, "submit")).json()["status"] == "pending_review"
    locked = await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "x", "reason": "Late change"},
        headers=editor.headers,
    )
    assert locked.status_code == 409
    assert (await act(client, editor, did, "approve")).status_code == 403  # editors cannot decide
    assert (await act(client, manager, did, "reject")).status_code == 422  # a reason is required
    rejected = await act(client, manager, did, "reject", comment="Use the full institute name.")
    assert (
        rejected.json()["status"] == "rejected" and rejected.json()["reviewed_by_id"] == manager.id
    )

    await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "Admissions | NASTP Institute of IT", "reason": "Full name."},
        headers=editor.headers,
    )
    assert (await act(client, editor, did, "submit")).status_code == 200
    approved = await act(client, manager, did, "approve", comment="Looks right.")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert approved.json()["reviewed_at"]

    assert (await act(client, manager, did, "rollback", comment="Too early")).status_code == 409
    published = await act(client, manager, did, "mark-published", comment="Updated in the CMS.")
    assert published.json()["status"] == "published" and published.json()["published_at"]
    assert (await act(client, manager, did, "rollback")).status_code == 422
    rolled = await act(client, manager, did, "rollback", comment="Old title restored in the CMS.")
    assert rolled.json()["status"] == "rolled_back" and rolled.json()["rolled_back_at"]
    assert (await act(client, manager, did, "mark-published")).status_code == 409
    assert (await act(client, manager, did, "reopen")).status_code == 409

    detail = (await client.get(f"/api/v1/drafts/{did}", headers=p["viewer"].headers)).json()
    assert [v["version"] for v in detail["versions"]] == [1, 2, 3]
    assert detail["versions"][0]["proposed_content"] == "Admissions | How to apply to NIIT"
    assert [t["action"] for t in detail["trail"]] == [
        "created", "edited", "submitted", "rejected", "edited", "submitted", "approved",
        "published", "rolled_back",
    ]  # fmt: skip
    assert detail["trail"][3]["comment"] == "Use the full institute name."
    assert detail["people"][manager.id] == "Seo Manager"
    assert detail["original_content"] == "Admissions"  # the original is always preserved

    audit = (
        await client.get(
            f"/api/v1/organisations/{org['id']}/audit-logs",
            params={"page_size": 100},
            headers=p["owner"].headers,
        )
    ).json()
    actions = {e["action"] for e in audit["items"]}
    assert {"draft.created", "draft.approved", "draft.published", "draft.rolled_back"} <= actions


async def test_reopen_and_listing(client: AsyncClient) -> None:
    _, project, p = await team(client)
    did = (await create(client, p["editor"], project["id"])).json()["id"]
    await act(client, p["editor"], did, "submit")
    await act(client, p["seo_manager"], did, "approve")
    reopened = await act(client, p["editor"], did, "reopen", comment="Needs another look.")
    assert reopened.json()["status"] == "draft" and reopened.json()["reviewed_by_id"] is None
    await create(client, p["editor"], project["id"], field="meta_description")
    url = f"/api/v1/projects/{project['id']}/drafts"
    assert (await client.get(url, headers=p["viewer"].headers)).json()["total"] == 2
    pending = await client.get(
        url, params={"status_filter": "pending_review"}, headers=p["viewer"].headers
    )
    assert pending.json()["total"] == 0


async def test_authors_and_submitters_cannot_approve_their_own_work(client: AsyncClient) -> None:
    _, project, p = await team(client)
    manager, owner = p["seo_manager"], p["owner"]
    did = (await create(client, manager, project["id"])).json()["id"]
    await act(client, manager, did, "submit")
    own = await act(client, manager, did, "approve")
    assert own.status_code == 403 and "cannot approve" in own.json()["error"]["message"]
    assert (await act(client, owner, did, "approve")).status_code == 200

    # The manager edits a draft the editor wrote: the manager is now the version author.
    did = (await create(client, p["editor"], project["id"])).json()["id"]
    await client.patch(
        f"/api/v1/drafts/{did}",
        json={"proposed_content": "Admissions at NIIT", "reason": "Reworded."},
        headers=manager.headers,
    )
    await act(client, p["editor"], did, "submit")
    assert (await act(client, manager, did, "approve")).status_code == 403
    assert (
        await act(client, p["editor"], did, "approve")
    ).status_code == 403  # submitter, and editor
    assert (await act(client, owner, did, "approve")).status_code == 200


async def test_official_facts_need_a_verified_source(client: AsyncClient) -> None:
    _, project, p = await team(client)
    created = await create(
        client,
        p["editor"],
        project["id"],
        field="meta_description",
        original_content="Apply to NIIT.",
        proposed_content="Apply to NIIT before 30 June 2026. Tuition fee: Rs. 95,000 per semester.",
    )
    draft = created.json()
    assert draft["protected"] is True
    reasons = " ".join(draft["protected_reasons"])
    assert "rs. 95,000" in reasons and "2026" in reasons and "fee" in reasons
    await act(client, p["editor"], draft["id"], "submit")
    blocked = await act(client, p["seo_manager"], draft["id"], "approve")
    assert blocked.status_code == 409 and "verified source" in blocked.json()["error"]["message"]
    approved = await act(
        client,
        p["seo_manager"],
        draft["id"],
        "approve",
        source_reference="Admissions office fee notice, reference AO-2026-07",
    )
    assert approved.status_code == 200
    assert (
        approved.json()["source_reference"] == "Admissions office fee notice, reference AO-2026-07"
    )


async def test_permissions_and_validation(client: AsyncClient) -> None:
    _, project, p = await team(client)
    assert (await create(client, p["viewer"], project["id"])).status_code == 403
    for bad in (
        {"field": "body_html"},
        {"proposed_content": ""},
        {"reason": "no"},
        {"unexpected": True},
    ):
        assert (await create(client, p["editor"], project["id"], **bad)).status_code == 422, bad
    for url in ("javascript:alert(1)", "https://other.example.com/", "ftp://example.org/x"):
        outside = await create(client, p["editor"], project["id"], page_url=url)
        assert outside.status_code == 400, url
    relative = await create(client, p["editor"], project["id"], page_url="/fees?year=next")
    assert relative.json()["page_url"] == "https://example.org/fees?year=next"
    sub = await create(client, p["editor"], project["id"], page_url="https://apply.example.org/")
    assert sub.status_code == 201
    unknown_issue = await create(
        client, p["editor"], project["id"], issue_ids=["11111111-2222-3333-4444-555555555555"]
    )
    assert unknown_issue.status_code == 400
    did = (await create(client, p["editor"], project["id"])).json()["id"]
    assert (await act(client, p["viewer"], did, "submit")).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/drafts/{did}",
            json={"proposed_content": "x", "reason": "Viewer edit"},
            headers=p["viewer"].headers,
        )
    ).status_code == 403
    assert (await act(client, p["seo_manager"], did, "approve")).status_code == 409  # not submitted
