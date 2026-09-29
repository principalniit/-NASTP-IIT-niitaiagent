"""Reports and schedules never cross organisation boundaries."""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.worker import process_next_report
from tests.conftest import add_member, make_org, make_project, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def test_reports_and_schedules_are_isolated(client: AsyncClient, site: FixtureSite) -> None:
    owner_b, _, project_b = await analysed(client, site)
    pid_b = project_b["id"]
    report_b = (
        await client.post(f"/api/v1/projects/{pid_b}/reports", json={}, headers=owner_b.headers)
    ).json()
    assert await process_next_report()

    alice = await make_user(client, "alice@example.org")
    org_a = await make_org(client, owner_b, "Org A")
    await add_member(client, owner_b, org_a["id"], alice, "owner")
    await make_project(client, alice, org_a["id"], "https://a.example.org")
    h = alice.headers
    for method, path, body in (
        ("GET", f"/api/v1/projects/{pid_b}/reports", None),
        ("POST", f"/api/v1/projects/{pid_b}/reports", {}),
        ("GET", f"/api/v1/reports/{report_b['id']}", None),
        ("GET", f"/api/v1/reports/{report_b['id']}/html", None),
        ("GET", f"/api/v1/reports/{report_b['id']}/pdf", None),
        ("DELETE", f"/api/v1/reports/{report_b['id']}", None),
        ("GET", f"/api/v1/projects/{pid_b}/schedule", None),
        ("PUT", f"/api/v1/projects/{pid_b}/schedule", {"enabled": True}),
    ):
        response = await client.request(method, path, json=body, headers=h)
        assert response.status_code == 404, (method, path, response.status_code)

    still_there = await client.get(f"/api/v1/reports/{report_b['id']}", headers=owner_b.headers)
    assert still_there.status_code == 200
    schedule = await client.get(f"/api/v1/projects/{pid_b}/schedule", headers=owner_b.headers)
    assert schedule.json()["enabled"] is False
