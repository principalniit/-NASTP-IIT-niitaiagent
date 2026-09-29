from httpx import AsyncClient

from tests.conftest import add_member, make_org, make_project, make_user


async def _setup(client: AsyncClient):  # type: ignore[no-untyped-def]
    owner = await make_user(client, "owner@example.org", platform_admin=True)
    org = await make_org(client, owner, "A")
    return owner, org


async def test_create_and_read_project_with_default_settings(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    project = await make_project(client, owner, org["id"], "NIIT.edu.pk/")
    assert project["root_url"] == "https://niit.edu.pk/"
    assert project["domain"] == "niit.edu.pk"

    fetched = await client.get(f"/api/v1/projects/{project['id']}", headers=owner.headers)
    assert fetched.status_code == 200
    settings = (
        await client.get(f"/api/v1/projects/{project['id']}/settings", headers=owner.headers)
    ).json()
    assert settings["settings"]["crawl"]["max_pages"] == 100
    assert settings["settings"]["crawl"]["max_depth"] == 5


async def test_project_url_validation_and_uniqueness(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    url = f"/api/v1/organisations/{org['id']}/projects"
    for bad in (
        "http://localhost",
        "http://169.254.169.254",
        "ftp://example.org",
        "http://10.1.1.1",
    ):
        response = await client.post(
            url, json={"name": "x", "root_url": bad}, headers=owner.headers
        )
        assert response.status_code == 422, bad
    await make_project(client, owner, org["id"], "https://example.org")
    dup = await client.post(
        url, json={"name": "x", "root_url": "https://EXAMPLE.org/other"}, headers=owner.headers
    )
    assert dup.status_code == 409


async def test_list_filter_sort_paginate(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    url = f"/api/v1/organisations/{org['id']}/projects"
    for name, site in (
        ("Charlie", "c.example.org"),
        ("Alpha", "a.example.org"),
        ("Bravo", "b.example.org"),
    ):
        await client.post(url, json={"name": name, "root_url": site}, headers=owner.headers)
    page = (await client.get(url, params={"page_size": 2}, headers=owner.headers)).json()
    assert [p["name"] for p in page["items"]] == ["Alpha", "Bravo"]
    assert page["total"] == 3
    desc = (
        await client.get(url, params={"sort": "name", "order": "desc"}, headers=owner.headers)
    ).json()
    assert desc["items"][0]["name"] == "Charlie"
    found = (await client.get(url, params={"q": "b.exa"}, headers=owner.headers)).json()
    assert [p["name"] for p in found["items"]] == ["Bravo"]
    wildcard = (await client.get(url, params={"q": "%"}, headers=owner.headers)).json()
    assert wildcard["total"] == 0
    bad_sort = await client.get(url, params={"sort": "password"}, headers=owner.headers)
    assert bad_sort.status_code == 422


async def test_update_and_soft_delete(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    project = await make_project(client, owner, org["id"])
    url = f"/api/v1/projects/{project['id']}"
    updated = await client.patch(
        url, json={"name": "Renamed", "root_url": "https://www.example.org"}, headers=owner.headers
    )
    assert updated.status_code == 200
    assert updated.json()["domain"] == "www.example.org"
    assert (await client.delete(url, headers=owner.headers)).status_code == 204
    assert (await client.get(url, headers=owner.headers)).status_code == 404
    # A deleted project frees its domain for a new project.
    await make_project(client, owner, org["id"], "https://www.example.org")


async def test_settings_update_respects_org_caps(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    project = await make_project(client, owner, org["id"])
    url = f"/api/v1/projects/{project['id']}/settings"
    current = (await client.get(url, headers=owner.headers)).json()["settings"]
    current["crawl"]["max_pages"] = 1000
    too_big = await client.put(url, json=current, headers=owner.headers)
    assert too_big.status_code == 400
    assert too_big.json()["error"]["details"][0]["loc"] == ["settings", "crawl", "max_pages"]
    current["crawl"]["max_pages"] = 250
    current["excluded_paths"] = ["/wp-admin/*"]
    current["content_types"] = [
        {"key": "admissions", "label": "Admissions", "url_patterns": ["/admissions/*"]}
    ]
    ok = await client.put(url, json=current, headers=owner.headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["settings"]["crawl"]["max_pages"] == 250


async def test_role_permissions_on_projects(client: AsyncClient) -> None:
    owner, org = await _setup(client)
    project = await make_project(client, owner, org["id"])
    manager = await make_user(client, "mgr@example.org")
    editor = await make_user(client, "ed@example.org")
    viewer = await make_user(client, "view@example.org")
    await add_member(client, owner, org["id"], manager, "seo_manager")
    await add_member(client, owner, org["id"], editor, "editor")
    await add_member(client, owner, org["id"], viewer, "viewer")
    create_url = f"/api/v1/organisations/{org['id']}/projects"
    body = {"name": "x", "root_url": "https://other.example.org"}
    assert (await client.post(create_url, json=body, headers=manager.headers)).status_code == 403
    assert (await client.post(create_url, json=body, headers=editor.headers)).status_code == 403

    settings_url = f"/api/v1/projects/{project['id']}/settings"
    current = (await client.get(settings_url, headers=viewer.headers)).json()["settings"]
    assert (
        await client.put(settings_url, json=current, headers=manager.headers)
    ).status_code == 200
    assert (await client.put(settings_url, json=current, headers=editor.headers)).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/projects/{project['id']}", json={"name": "y"}, headers=viewer.headers
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/projects/{project['id']}", headers=manager.headers)
    ).status_code == 403
