"""A user must never reach another organisation's data by changing an ID."""

import uuid

from httpx import AsyncClient

from tests.conftest import add_member, make_org, make_project, make_user


async def _two_tenants(client: AsyncClient):  # type: ignore[no-untyped-def]
    platform = await make_user(client, "platform@example.org", platform_admin=True)
    alice = await make_user(client, "alice@example.org")
    bob = await make_user(client, "bob@example.org")
    org_a = await make_org(client, platform, "Org A")
    org_b = await make_org(client, platform, "Org B")
    await add_member(client, platform, org_a["id"], alice, "owner")
    await add_member(client, platform, org_b["id"], bob, "owner")
    project_b = await make_project(client, bob, org_b["id"], "https://b.example.org")
    members_b = (
        await client.get(f"/api/v1/organisations/{org_b['id']}/members", headers=bob.headers)
    ).json()
    return platform, alice, bob, org_a, org_b, project_b, members_b["items"][0]


async def test_cross_tenant_reads_return_404(client: AsyncClient) -> None:
    _, alice, _, _, org_b, project_b, _ = await _two_tenants(client)
    for path in (
        f"/api/v1/organisations/{org_b['id']}",
        f"/api/v1/organisations/{org_b['id']}/members",
        f"/api/v1/organisations/{org_b['id']}/projects",
        f"/api/v1/organisations/{org_b['id']}/audit-logs",
        f"/api/v1/projects/{project_b['id']}",
        f"/api/v1/projects/{project_b['id']}/settings",
    ):
        response = await client.get(path, headers=alice.headers)
        assert response.status_code == 404, path


async def test_cross_tenant_writes_return_404_and_change_nothing(client: AsyncClient) -> None:
    _, alice, bob, org_a, org_b, project_b, member_b = await _two_tenants(client)
    h = alice.headers
    assert (
        await client.patch(
            f"/api/v1/organisations/{org_b['id']}", json={"name": "pwned"}, headers=h
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/organisations/{org_b['id']}/projects",
            json={"name": "x", "root_url": "https://x.example.org"},
            headers=h,
        )
    ).status_code == 404
    assert (
        await client.patch(f"/api/v1/projects/{project_b['id']}", json={"name": "pwned"}, headers=h)
    ).status_code == 404
    assert (
        await client.put(f"/api/v1/projects/{project_b['id']}/settings", json={}, headers=h)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/projects/{project_b['id']}", headers=h)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/organisations/{org_b['id']}/members",
            json={"email": alice.email, "role": "owner"},
            headers=h,
        )
    ).status_code == 404
    # Mixing Alice's organisation ID with Bob's member ID must not reach Bob's membership.
    mixed = await client.patch(
        f"/api/v1/organisations/{org_a['id']}/members/{member_b['id']}",
        json={"role": "viewer"},
        headers=h,
    )
    assert mixed.status_code == 404
    mixed_delete = await client.delete(
        f"/api/v1/organisations/{org_a['id']}/members/{member_b['id']}", headers=h
    )
    assert mixed_delete.status_code == 404

    project = (await client.get(f"/api/v1/projects/{project_b['id']}", headers=bob.headers)).json()
    assert project["name"] == "Site"
    members = (
        await client.get(f"/api/v1/organisations/{org_b['id']}/members", headers=bob.headers)
    ).json()
    # Org B still has exactly its creator and Bob, both owners, and Alice was not added.
    assert members["total"] == 2
    assert {m["user"]["email"] for m in members["items"]} == {"platform@example.org", bob.email}
    assert all(m["role"] == "owner" for m in members["items"])


async def test_unknown_ids_look_the_same_as_foreign_ids(client: AsyncClient) -> None:
    _, alice, _, _, _, project_b, _ = await _two_tenants(client)
    foreign = await client.get(f"/api/v1/projects/{project_b['id']}", headers=alice.headers)
    unknown = await client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=alice.headers)
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json()["error"] == unknown.json()["error"]


async def test_platform_admin_has_no_implicit_project_access(client: AsyncClient) -> None:
    platform, _, _, _, org_b, project_b, _ = await _two_tenants(client)
    # Platform admin created both orgs, so is owner there; use a second platform admin.
    other_admin = await make_user(client, "ops@example.org", platform_admin=True)
    assert (
        await client.get(f"/api/v1/organisations/{org_b['id']}", headers=other_admin.headers)
    ).status_code == 200
    assert (
        await client.get(
            f"/api/v1/organisations/{org_b['id']}/projects", headers=other_admin.headers
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/projects/{project_b['id']}", headers=other_admin.headers)
    ).status_code == 404
    assert platform.email


async def test_removed_member_loses_access_immediately(client: AsyncClient) -> None:
    platform = await make_user(client, "platform@example.org", platform_admin=True)
    carol = await make_user(client, "carol@example.org")
    org = await make_org(client, platform, "Org C")
    member = await add_member(client, platform, org["id"], carol, "seo_manager")
    project = await make_project(client, platform, org["id"])
    assert (
        await client.get(f"/api/v1/projects/{project['id']}", headers=carol.headers)
    ).status_code == 200
    await client.delete(
        f"/api/v1/organisations/{org['id']}/members/{member['id']}", headers=platform.headers
    )
    assert (
        await client.get(f"/api/v1/projects/{project['id']}", headers=carol.headers)
    ).status_code == 404


async def test_malformed_ids_are_rejected(client: AsyncClient) -> None:
    alice = await make_user(client, "alice@example.org")
    for path in (
        "/api/v1/projects/1",
        "/api/v1/projects/' OR 1=1 --",
        "/api/v1/organisations/../users",
    ):
        response = await client.get(path, headers=alice.headers)
        assert response.status_code in (404, 422), path
