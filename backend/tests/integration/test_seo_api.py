"""SEO engine through the API: issues, triage, scores, schema findings, link suggestions."""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.worker import process_next_analysis, process_next_job
from tests.conftest import add_member, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_crawl_api import engine_for, setup


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def crawled(client: AsyncClient, site: FixtureSite):  # type: ignore[no-untyped-def]
    owner, org, project = await setup(client, site)
    crawl = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()
    await process_next_job("w", engine_factory=engine_for(site))
    assert await process_next_analysis()
    return owner, org, project, crawl


async def test_issues_scores_and_results(client: AsyncClient, site: FixtureSite) -> None:
    owner, _, project, crawl = await crawled(client, site)
    h = owner.headers
    job = (await client.get(f"/api/v1/crawls/{crawl['id']}", headers=h)).json()
    assert job["analysis_status"] == "completed" and job["analysed_at"]

    base = f"/api/v1/projects/{project['id']}/issues"
    issues = (await client.get(base, params={"page_size": 100}, headers=h)).json()
    assert issues["total"] > 5
    priorities = [i["priority_score"] for i in issues["items"]]
    assert priorities == sorted(priorities, reverse=True)
    assert all(
        i["evidence"] and i["recommendation"] and i["resolution_status"] == "open"
        for i in issues["items"]
    )

    high = (await client.get(base, params={"severity": "high"}, headers=h)).json()
    assert high["total"] >= 1 and {i["severity"] for i in high["items"]} == {"high"}
    tech = (
        await client.get(base, params={"category": "technical", "sort": "severity"}, headers=h)
    ).json()
    assert {i["category"] for i in tech["items"]} == {"technical"}
    order = ["critical", "high", "medium", "low", "informational"]
    ranks = [order.index(i["severity"]) for i in tech["items"]]
    assert ranks == sorted(ranks)
    missing = (
        await client.get(
            base, params={"q": "/missing", "rule_id": "tech.http_client_error"}, headers=h
        )
    ).json()
    assert missing["total"] == 1

    summary = (await client.get(f"{base}/summary", headers=h)).json()
    assert summary["latest_crawl_id"] == crawl["id"]
    assert summary["open_total"] == issues["total"]
    assert summary["new_in_latest"] == issues["total"]
    assert sum(summary["open_by_severity"].values()) == issues["total"]

    score = (await client.get(f"/api/v1/crawls/{crawl['id']}/score", headers=h)).json()
    assert 0 <= score["overall"] <= 100
    assert score["breakdown"]["categories"]["technical"]["contributions"]
    history = (await client.get(f"/api/v1/projects/{project['id']}/scores", headers=h)).json()
    assert [p["crawl_job_id"] for p in history] == [crawl["id"]]

    recs = (
        await client.get(f"/api/v1/crawls/{crawl['id']}/link-recommendations", headers=h)
    ).json()
    assert recs["total"] == 1
    assert recs["items"][0]["target_url"].endswith("/orphan")
    assert "Scholarship Opportunities" in recs["items"][0]["snippet"]
    schema = (await client.get(f"/api/v1/crawls/{crawl['id']}/schema-findings", headers=h)).json()
    assert schema["total"] == 0

    org_id = project["organisation_id"]
    analysed = (
        await client.get(
            f"/api/v1/organisations/{org_id}/crawls", params={"analysed": "true"}, headers=h
        )
    ).json()
    assert [c["id"] for c in analysed["items"]] == [crawl["id"]]
    pending = (
        await client.get(
            f"/api/v1/organisations/{org_id}/crawls", params={"analysed": "false"}, headers=h
        )
    ).json()
    assert pending["total"] == 0

    rules = (await client.get("/api/v1/seo-rules", headers=h)).json()
    assert len(rules) == 50 and all(r["recommendation"] for r in rules)


async def test_triage_rules_and_permissions(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project, _ = await crawled(client, site)
    viewer = await make_user(client, "viewer@example.org")
    editor = await make_user(client, "editor@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    await add_member(client, owner, org["id"], editor, "editor")
    issue = (
        await client.get(f"/api/v1/projects/{project['id']}/issues", headers=viewer.headers)
    ).json()["items"][0]
    url = f"/api/v1/issues/{issue['id']}"

    assert (await client.get(url, headers=viewer.headers)).status_code == 200
    denied = await client.patch(url, json={"resolution_status": "ignored"}, headers=viewer.headers)
    assert denied.status_code == 403
    ignored = await client.patch(
        url, json={"resolution_status": "ignored", "note": "Intentional"}, headers=editor.headers
    )
    assert ignored.status_code == 200 and ignored.json()["resolution_status"] == "ignored"
    assert ignored.json()["triage_note"] == "Intentional"
    manual = await client.patch(url, json={"resolution_status": "resolved"}, headers=editor.headers)
    assert manual.status_code == 422  # only a crawl can resolve an issue

    listed = (
        await client.get(
            f"/api/v1/projects/{project['id']}/issues",
            params={"status": "ignored"},
            headers=owner.headers,
        )
    ).json()
    assert [i["id"] for i in listed["items"]] == [issue["id"]]
    everything = (
        await client.get(
            f"/api/v1/projects/{project['id']}/issues",
            params={"all_statuses": "true", "page_size": 100},
            headers=owner.headers,
        )
    ).json()
    assert issue["id"] in {i["id"] for i in everything["items"]}
    reopened = await client.patch(url, json={"resolution_status": "open"}, headers=owner.headers)
    assert reopened.json()["resolution_status"] == "open"

    logs = (
        await client.get(
            f"/api/v1/organisations/{org['id']}/audit-logs",
            params={"action": "issue."},
            headers=owner.headers,
        )
    ).json()
    assert logs["total"] == 2


async def test_reanalysis_rules(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project, crawl = await crawled(client, site)
    viewer = await make_user(client, "viewer@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    url = f"/api/v1/crawls/{crawl['id']}/analyse"
    assert (await client.post(url, headers=viewer.headers)).status_code == 403
    queued = await client.post(url, headers=owner.headers)
    assert queued.status_code == 202 and queued.json()["analysis_status"] == "queued"
    assert (await client.post(url, headers=owner.headers)).status_code == 409
    assert await process_next_analysis()

    second = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()
    not_done = await client.post(f"/api/v1/crawls/{second['id']}/analyse", headers=owner.headers)
    assert not_done.status_code == 409
    await process_next_job("w", engine_factory=engine_for(site))
    older = await client.post(url, headers=owner.headers)
    assert older.status_code == 409  # a newer crawl exists


async def test_score_for_unanalysed_crawl_is_404(client: AsyncClient, site: FixtureSite) -> None:
    owner, _, project = await setup(client, site)
    crawl = (
        await client.post(f"/api/v1/projects/{project['id']}/crawls", headers=owner.headers)
    ).json()
    response = await client.get(f"/api/v1/crawls/{crawl['id']}/score", headers=owner.headers)
    assert response.status_code == 404
    summary = (
        await client.get(f"/api/v1/projects/{project['id']}/issues/summary", headers=owner.headers)
    ).json()
    assert summary["latest_crawl_id"] is None and summary["open_total"] == 0
