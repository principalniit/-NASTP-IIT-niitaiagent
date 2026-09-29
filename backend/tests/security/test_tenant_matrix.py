"""Multi-tenant verification suite.

Instead of hand-listing endpoints, this walks every route in the OpenAPI schema. Each
route that takes an id is called with ids from another organisation, and must answer
404. A new route with an id parameter the suite does not know fails the test, so tenant
isolation is checked for endpoints nobody has written a test for yet.
"""

import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import Base, get_session_factory
from app.modules.ai.models import AIAnalysis, AIKind, AIStatus, SeoRecommendation
from app.modules.crawler.models import CrawlJob, CrawlPage
from app.modules.drafts.models import ContentDraft
from app.modules.integrations.models import Integration
from app.modules.organisations.models import OrganisationMember
from app.modules.projects.models import Project
from app.modules.reports.models import Report
from app.modules.seo.models import SeoIssue
from app.worker import process_next_report
from tests.conftest import add_member, make_org, make_project, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed

# Tables that are not owned by one organisation.
GLOBAL_TABLES = {"users", "refresh_tokens", "organisations", "audit_logs", "plans"}
PARAM = re.compile(r"{(\w+)}")
# Platform-wide administration routes: not owned by any organisation, so a non-admin
# gets 403 rather than 404. test_global_routes_need_a_platform_admin covers them.
GLOBAL_ROUTES = {"/api/v1/plans/{plan_id}"}


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


def test_every_tenant_table_carries_organisation_id() -> None:
    missing = [
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in GLOBAL_TABLES
        and ("organisation_id" not in table.c or table.c.organisation_id.nullable)
    ]
    assert missing == [], f"Tenant tables without a required organisation_id: {missing}"


async def _victim(client: AsyncClient, site: FixtureSite) -> dict[str, str]:
    """Organisation B with at least one record of every kind that has its own route."""
    owner_b, org_b, project_b = await analysed(client, site)
    pid = project_b["id"]
    member = await make_user(client, "member-b@example.org")
    await add_member(client, owner_b, org_b["id"], member, "editor")
    draft = await client.post(
        f"/api/v1/projects/{pid}/drafts",
        json={
            "page_url": "/about",
            "field": "title",
            "proposed_content": "About NIIT",
            "reason": "Clearer title",
        },
        headers=owner_b.headers,
    )
    assert draft.status_code == 201, draft.text
    report = await client.post(f"/api/v1/projects/{pid}/reports", json={}, headers=owner_b.headers)
    assert report.status_code == 202 and await process_next_report()

    async with get_session_factory()() as session:
        project = uuid.UUID(pid)
        crawl = await session.scalar(select(CrawlJob).where(CrawlJob.project_id == project))
        page = await session.scalar(select(CrawlPage).where(CrawlPage.crawl_job_id == crawl.id))  # type: ignore[union-attr]
        issue = await session.scalar(select(SeoIssue).where(SeoIssue.project_id == project))
        membership = await session.scalar(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == uuid.UUID(org_b["id"]),
                OrganisationMember.user_id == uuid.UUID(member.id),
            )
        )
        assert crawl and page and issue and membership
        analysis = AIAnalysis(
            organisation_id=crawl.organisation_id,
            project_id=project,
            crawl_job_id=crawl.id,
            kind=AIKind.ISSUE_EXPLANATION,
            status=AIStatus.COMPLETED,
            subject_type="issue",
            subject_id=str(issue.id),
            finished_at=datetime.now(UTC),
        )
        session.add(analysis)
        await session.flush()
        integration = Integration(
            organisation_id=crawl.organisation_id, provider="webhook", name="Hook", config={}
        )
        session.add(integration)
        recommendation = SeoRecommendation(
            organisation_id=crawl.organisation_id,
            project_id=project,
            ai_analysis_id=analysis.id,
            title="Fix the page",
            body="Restore it.",
        )
        session.add(recommendation)
        await session.commit()
        return {
            "organisation_id": org_b["id"],
            "project_id": pid,
            "crawl_id": str(crawl.id),
            "page_id": str(page.id),
            "issue_id": str(issue.id),
            "draft_id": draft.json()["id"],
            "analysis_id": str(analysis.id),
            "recommendation_id": str(recommendation.id),
            "report_id": report.json()["id"],
            "member_id": str(membership.id),
            "integration_id": str(integration.id),
        }


async def _counts() -> dict[str, int]:
    async with get_session_factory()() as session:
        return {
            model.__name__: await session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Project, CrawlJob, SeoIssue, ContentDraft, Report, OrganisationMember)
        }


def _routes(app) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    spec = app.openapi()
    return [
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        if PARAM.search(path) and path not in GLOBAL_ROUTES
        for method in operations
    ]


async def test_every_scoped_route_refuses_other_organisations(
    client: AsyncClient,
    site: FixtureSite,
    app,  # type: ignore[no-untyped-def]
) -> None:
    ids = await _victim(client, site)
    project_b = await client.get(f"/api/v1/projects/{ids['project_id']}", headers={})
    assert project_b.status_code == 401

    # Alice owns another organisation: the strongest role, but not a member of B.
    alice = await make_user(client, "alice@example.org")
    admin = await make_user(client, "admin-a@example.org", platform_admin=True)
    org_a = await make_org(client, admin, "Org A")
    await add_member(client, admin, org_a["id"], alice, "owner")
    await make_project(client, alice, org_a["id"], "https://a.example.org")
    before = await _counts()

    checked = []
    for method, template in _routes(app):
        names = PARAM.findall(template)
        unknown = [n for n in names if n not in ids]
        assert not unknown, f"{method} {template}: add a record for {unknown} to this suite"
        path = PARAM.sub(lambda m: ids[m.group(1)], template)
        body = {} if method in {"POST", "PUT", "PATCH"} else None
        response = await client.request(method, path, json=body, headers=alice.headers)
        assert response.status_code == 404, f"{method} {template} returned {response.status_code}"
        checked.append((method, template))

    assert len(checked) >= 50, "the route walk found fewer routes than expected"
    assert await _counts() == before, "a foreign request changed data"


async def test_platform_admins_have_no_implicit_project_access(
    client: AsyncClient,
    site: FixtureSite,
    app,  # type: ignore[no-untyped-def]
) -> None:
    ids = await _victim(client, site)
    operator = await make_user(client, "operator@example.org", platform_admin=True)
    for method, template in _routes(app):
        if "{organisation_id}" in template or method != "GET":
            continue  # organisation administration is a platform admin duty
        path = PARAM.sub(lambda m: ids[m.group(1)], template)
        response = await client.get(path, headers=operator.headers)
        assert response.status_code == 404, f"GET {template} returned {response.status_code}"


async def test_global_routes_need_a_platform_admin(client: AsyncClient) -> None:
    owner = await make_user(client, "owner@example.org")
    for method, path, body in (
        ("GET", "/api/v1/plans", None),
        ("POST", "/api/v1/plans", {"key": "x", "name": "X plan"}),
        ("PATCH", f"/api/v1/plans/{uuid.uuid4()}", {"name": "Renamed"}),
    ):
        response = await client.request(method, path, json=body, headers=owner.headers)
        assert response.status_code == 403, (method, path, response.status_code)
