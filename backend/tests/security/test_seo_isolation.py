"""SEO results never cross organisation boundaries."""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.worker import process_next_analysis, process_next_job
from tests.conftest import add_member, make_org, make_project, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_crawl_api import engine_for, setup


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def test_seo_results_are_isolated(client: AsyncClient, site: FixtureSite) -> None:
    owner_b, _, project_b = await setup(client, site)
    crawl_b = (
        await client.post(f"/api/v1/projects/{project_b['id']}/crawls", headers=owner_b.headers)
    ).json()
    await process_next_job("w", engine_factory=engine_for(site))
    await process_next_analysis()
    issue_b = (
        await client.get(f"/api/v1/projects/{project_b['id']}/issues", headers=owner_b.headers)
    ).json()["items"][0]

    alice = await make_user(client, "alice@example.org")
    org_a = await make_org(client, owner_b, "Org A")
    await add_member(client, owner_b, org_a["id"], alice, "owner")
    # Alice belongs only to Org A; the project, crawl and issue below belong to Org B.
    await make_project(client, alice, org_a["id"], "https://a.example.org")
    h = alice.headers
    for method, path in (
        ("GET", f"/api/v1/projects/{project_b['id']}/issues"),
        ("GET", f"/api/v1/projects/{project_b['id']}/issues/summary"),
        ("GET", f"/api/v1/projects/{project_b['id']}/scores"),
        ("GET", f"/api/v1/issues/{issue_b['id']}"),
        ("GET", f"/api/v1/crawls/{crawl_b['id']}/score"),
        ("GET", f"/api/v1/crawls/{crawl_b['id']}/schema-findings"),
        ("GET", f"/api/v1/crawls/{crawl_b['id']}/link-recommendations"),
        ("POST", f"/api/v1/crawls/{crawl_b['id']}/analyse"),
    ):
        response = await client.request(method, path, headers=h)
        assert response.status_code == 404, path
    patched = await client.patch(
        f"/api/v1/issues/{issue_b['id']}", json={"resolution_status": "ignored"}, headers=h
    )
    assert patched.status_code == 404
    unchanged = (
        await client.get(f"/api/v1/issues/{issue_b['id']}", headers=owner_b.headers)
    ).json()
    assert unchanged["resolution_status"] == "open"

    ops = await make_user(client, "ops@example.org", platform_admin=True)
    assert (
        await client.get(f"/api/v1/issues/{issue_b['id']}", headers=ops.headers)
    ).status_code == 404
