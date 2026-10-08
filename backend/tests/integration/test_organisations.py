from httpx import AsyncClient

from tests.conftest import add_member, make_org, make_user


async def test_only_platform_admin_can_create_organisation(client: AsyncClient) -> None:
    user = await make_user(client, "user@example.org")
    denied = await client.post("/api/v1/organisations", json={"name": "Acme"}, headers=user.headers)
    assert denied.status_code == 403

    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "NASTP Institute of Information Technology")
    assert org["slug"] == "nastp-institute-of-information-technology"
    assert org["my_role"] == "owner"
    assert org["settings"]["crawl_limits"]["max_pages"] == 500
    again = await make_org(client, admin, "NASTP Institute of Information Technology")
    assert again["slug"].endswith("-2")


async def test_list_shows_only_my_organisations(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    member = await make_user(client, "m@example.org")
    org_a = await make_org(client, admin, "A")
    await make_org(client, admin, "B")
    await add_member(client, admin, org_a["id"], member, "viewer")

    mine = (await client.get("/api/v1/organisations", headers=member.headers)).json()
    assert [o["name"] for o in mine["items"]] == ["A"]
    assert mine["items"][0]["my_role"] == "viewer"
    assert "projects:create" not in mine["items"][0]["my_permissions"]

    everything = (await client.get("/api/v1/organisations", headers=admin.headers)).json()
    assert everything["total"] == 2


async def test_update_organisation_settings(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "A")
    url = f"/api/v1/organisations/{org['id']}"
    ok = await client.patch(
        url,
        json={
            "timezone": "Asia/Karachi",
            "settings": {
                "brand_tone": "Formal and clear",
                "approved_terminology": [{"preferred": "BS Computer Science", "avoid": ["BSCS"]}],
                "crawl_limits": {"max_pages": 200},
            },
        },
        headers=admin.headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["settings"]["crawl_limits"]["max_pages"] == 200
    assert ok.json()["timezone"] == "Asia/Karachi"

    bad = await client.patch(
        url, json={"settings": {"ai": {"provider": "openai"}}}, headers=admin.headers
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"
    null_name = await client.patch(url, json={"name": None}, headers=admin.headers)
    assert null_name.status_code == 422


async def test_member_management_rules(client: AsyncClient) -> None:
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    admin = await make_user(client, "orgadmin@example.org")
    viewer = await make_user(client, "viewer@example.org")
    org = await make_org(client, owner, "A")
    base = f"/api/v1/organisations/{org['id']}/members"
    admin_member = await add_member(client, owner, org["id"], admin, "admin")
    await add_member(client, owner, org["id"], viewer, "viewer")

    duplicate = await client.post(
        base, json={"email": viewer.email, "role": "editor"}, headers=owner.headers
    )
    assert duplicate.status_code == 409

    # Viewers cannot manage members.
    denied = await client.post(
        base, json={"email": "x@example.org", "role": "viewer"}, headers=viewer.headers
    )
    assert denied.status_code == 403

    # Admins cannot grant the owner role.
    grant_owner = await client.post(
        base,
        json={
            "email": "new@example.org",
            "role": "owner",
            "full_name": "New",
            "password": "a-long-password",
        },
        headers=admin.headers,
    )
    assert grant_owner.status_code == 403

    # Adding an unknown email requires account details.
    missing = await client.post(
        base, json={"email": "new@example.org", "role": "editor"}, headers=admin.headers
    )
    assert missing.status_code == 400
    created = await client.post(
        base,
        json={
            "email": "new@example.org",
            "role": "editor",
            "full_name": "New",
            "password": "a-long-password",
        },
        headers=admin.headers,
    )
    assert created.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": "new@example.org", "password": "a-long-password"}
    )
    assert login.status_code == 200

    members = (await client.get(base, headers=viewer.headers)).json()
    assert members["total"] == 4
    owner_member = next(m for m in members["items"] if m["role"] == "owner")

    # The last owner cannot be demoted or removed.
    demote = await client.patch(
        f"{base}/{owner_member['id']}", json={"role": "admin"}, headers=owner.headers
    )
    assert demote.status_code == 409
    remove = await client.delete(f"{base}/{owner_member['id']}", headers=owner.headers)
    assert remove.status_code == 409

    # Admins cannot modify an owner.
    touch_owner = await client.patch(
        f"{base}/{owner_member['id']}", json={"role": "viewer"}, headers=admin.headers
    )
    assert touch_owner.status_code == 403

    promote = await client.patch(
        f"{base}/{admin_member['id']}", json={"role": "seo_manager"}, headers=owner.headers
    )
    assert promote.status_code == 200
    assert promote.json()["role"] == "seo_manager"
    removed = await client.delete(f"{base}/{admin_member['id']}", headers=owner.headers)
    assert removed.status_code == 204


async def test_audit_log_records_changes_and_is_restricted(client: AsyncClient) -> None:
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    viewer = await make_user(client, "viewer@example.org")
    org = await make_org(client, owner, "A")
    await add_member(client, owner, org["id"], viewer, "viewer")
    url = f"/api/v1/organisations/{org['id']}/audit-logs"
    logs = (await client.get(url, headers=owner.headers)).json()
    actions = [entry["action"] for entry in logs["items"]]
    assert actions == ["member.added", "organisation.created"]
    assert all(entry["request_id"] for entry in logs["items"])
    filtered = (await client.get(url, params={"action": "member."}, headers=owner.headers)).json()
    assert filtered["total"] == 1
    assert (await client.get(url, headers=viewer.headers)).status_code == 403
