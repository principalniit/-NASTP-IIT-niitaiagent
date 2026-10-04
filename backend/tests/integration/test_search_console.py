"""Google Search Console: key handling, connection test, sync, project figures and the AI."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.search_data import google
from app.modules.search_data.models import SearchPageDay, SearchPageQuery, SearchSync
from app.modules.search_data.service import queue_due_syncs
from app.worker import process_next_search_sync
from tests.conftest import TestUser, add_member, make_org, make_project, make_user

PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = PRIVATE.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
EMAIL = "seo-reader@niit-seo.iam.gserviceaccount.com"
KEY = json.dumps(
    {
        "type": "service_account",
        "client_email": EMAIL,
        "private_key": PEM,
        "private_key_id": "k1",
        # A tampered key must not redirect the server; this address is never used.
        "token_uri": "http://169.254.169.254/latest",
    }
)
PROPERTY = "sc-domain:example.org"


def _day(n: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=n)).isoformat()


class FakeGoogle:
    """Google's token and Search Console endpoints, checking what the server sends."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_status = 200
        self.site_status = 200
        self.permission = "siteFullUser"
        self.day_rows: list[dict[str, Any]] = [
            {
                "keys": [_day(2), "https://example.org/"],
                "clicks": 40,
                "impressions": 1000,
                "position": 3.0,
            },
            {
                "keys": [_day(2), "https://example.org/admissions"],
                "clicks": 10,
                "impressions": 500,
                "position": 6.0,
            },
            {
                "keys": [_day(3), "https://example.org/"],
                "clicks": 30,
                "impressions": 900,
                "position": 4.0,
            },
            # Another host in the same domain property belongs to another project.
            {
                "keys": [_day(2), "https://lms.example.org/"],
                "clicks": 99,
                "impressions": 99,
                "position": 1.0,
            },
        ]
        self.query_rows: list[dict[str, Any]] = [
            {
                "keys": ["https://example.org/", "example org"],
                "clicks": 50,
                "impressions": 1200,
                "position": 2.5,
            },
            {
                "keys": ["https://example.org/admissions", "example admissions"],
                "clicks": 10,
                "impressions": 500,
                "position": 6.0,
            },
            {
                "keys": ["https://example.org/", "example fees"],
                "clicks": 20,
                "impressions": 700,
                "position": 5.0,
            },
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        settings = get_settings()
        if str(request.url) == settings.google_token_url:
            form = dict(httpx.QueryParams(request.content.decode()))
            claims = jwt.decode(
                form["assertion"],
                PRIVATE.public_key(),
                algorithms=["RS256"],
                audience=settings.google_token_url,
            )
            assert claims["iss"] == EMAIL and claims["scope"].endswith("webmasters.readonly")
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        assert str(request.url).startswith(settings.google_search_console_url)
        if request.url.path.endswith("/searchAnalytics/query"):
            body = json.loads(request.content)
            rows = self.day_rows if body["dimensions"] == ["date", "page"] else self.query_rows
            start = body["startRow"]
            return httpx.Response(200, json={"rows": rows[start : start + body["rowLimit"]]})
        if self.site_status != 200:
            return httpx.Response(self.site_status, json={"error": {"message": "no"}})
        return httpx.Response(200, json={"siteUrl": PROPERTY, "permissionLevel": self.permission})


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeGoogle]:
    fake = FakeGoogle()
    monkeypatch.setattr(google, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(get_settings(), "integrations_encryption_keys", _fernet())
    yield fake


def _fernet():  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    return SecretStr(Fernet.generate_key().decode())


async def _org(client: AsyncClient) -> tuple[TestUser, dict, dict]:  # type: ignore[type-arg]
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    owner = await make_user(client, "owner@example.org")
    await add_member(client, admin, org["id"], owner, "owner")
    project = await make_project(client, owner, org["id"], "https://example.org")
    return owner, org, project


async def _integration(client: AsyncClient, owner: TestUser, org: dict, secret: str = KEY) -> Any:  # type: ignore[type-arg]
    return await client.post(
        f"/api/v1/organisations/{org['id']}/integrations",
        json={
            "provider": "google_search_console",
            "name": "Search Console",
            "config": {"property_url": PROPERTY},
            "secret": secret,
        },
        headers=owner.headers,
    )


def test_keys_are_checked_before_use() -> None:
    assert google.parse_key(KEY).client_email == EMAIL
    for bad, message in (
        ("not json", "not a JSON key"),
        (json.dumps({"type": "authorized_user"}), "service account key"),
        (json.dumps({"type": "service_account", "client_email": "x@gmail.com"}), "email"),
        (json.dumps({"type": "service_account", "client_email": EMAIL}), "private key"),
    ):
        with pytest.raises(google.SearchConsoleError, match=message):
            google.parse_key(bad)


async def test_connecting_syncing_and_reading_figures(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    owner, org, project = await _org(client)
    perf_url = f"/api/v1/projects/{project['id']}/search-performance"
    empty = (await client.get(perf_url, headers=owner.headers)).json()
    assert empty["state"] == "not_connected" and empty["totals"] is None

    wrong = await _integration(client, owner, org, secret='{"type": "authorized_user"}')
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "invalid_credential"
    created = await _integration(client, owner, org)
    assert created.status_code == 201, created.text
    integration = created.json()
    assert integration["config"]["service_account_email"] == EMAIL
    assert integration["secret_hint"] == "set" and "private_key" not in created.text
    base = f"/api/v1/integrations/{integration['id']}/search-console"

    tested = await client.post(f"{base}/test", headers=owner.headers)
    assert tested.json() == {"permission_level": "siteFullUser", "service_account_email": EMAIL}
    token_calls = [r for r in fake_google.requests if "169.254" in str(r.url)]
    assert token_calls == [], "the key's own token address must never be used"

    fake_google.site_status = 403
    refused = await client.post(f"{base}/test", headers=owner.headers)
    assert refused.status_code == 400 and "Add its email" in refused.json()["error"]["message"]
    fake_google.site_status = 200

    connected = (await client.get(perf_url, headers=owner.headers)).json()
    assert connected["state"] == "no_data" and connected["connected"]

    queued = await client.post(f"{base}/syncs", headers=owner.headers)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    again = await client.post(f"{base}/syncs", headers=owner.headers)
    assert again.status_code == 409
    assert await process_next_search_sync()
    syncs = (await client.get(f"{base}/syncs", headers=owner.headers)).json()
    assert syncs[0]["status"] == "succeeded" and syncs[0]["page_day_rows"] == 4

    perf = (await client.get(perf_url, headers=owner.headers)).json()
    assert perf["state"] == "ready" and perf["properties"] == [PROPERTY]
    # Only example.org rows; lms.example.org belongs to another project.
    assert perf["totals"] == {
        "clicks": 80,
        "impressions": 2400,
        "ctr": round(80 / 2400, 4),
        "position": round((3 * 1000 + 6 * 500 + 4 * 900) / 2400, 1),
    }
    assert [d["clicks"] for d in perf["daily"]] == [30, 50]
    assert perf["top_pages"][0]["page"] == "https://example.org/"
    assert perf["top_pages"][0]["clicks"] == 70
    assert [q["query"] for q in perf["top_queries"]] == [
        "example org",
        "example fees",
        "example admissions",
    ]

    page = await client.get(
        f"{perf_url}/page",
        params={"url": "https://example.org/admissions"},
        headers=owner.headers,
    )
    assert page.json()["totals"]["clicks"] == 10
    assert [q["query"] for q in page.json()["top_queries"]] == ["example admissions"]

    # A second sync replaces the period instead of adding to it.
    await client.post(f"{base}/syncs", headers=owner.headers)
    assert await process_next_search_sync()
    async with get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(SearchPageDay)) == 4
        assert await session.scalar(select(func.count()).select_from(SearchPageQuery)) == 3


async def test_sync_failures_are_explained(client: AsyncClient, fake_google: FakeGoogle) -> None:
    owner, org, _ = await _org(client)
    integration = (await _integration(client, owner, org)).json()
    fake_google.token_status = 401
    await client.post(
        f"/api/v1/integrations/{integration['id']}/search-console/syncs", headers=owner.headers
    )
    assert await process_next_search_sync()
    async with get_session_factory()() as session:
        sync = await session.scalar(select(SearchSync))
        assert sync is not None and sync.status == "failed"
        assert sync.error and "rejected the service account key" in sync.error


async def test_only_managers_sync_and_any_member_reads(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    owner, org, project = await _org(client)
    viewer = await make_user(client, "viewer@example.org")
    await add_member(client, owner, org["id"], viewer, "viewer")
    integration = (await _integration(client, owner, org)).json()
    sync = await client.post(
        f"/api/v1/integrations/{integration['id']}/search-console/syncs", headers=viewer.headers
    )
    assert sync.status_code == 403
    read = await client.get(
        f"/api/v1/projects/{project['id']}/search-performance", headers=viewer.headers
    )
    assert read.status_code == 200


async def test_enabled_integrations_sync_daily(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    owner, org, _ = await _org(client)
    integration = (await _integration(client, owner, org)).json()
    factory = get_session_factory()
    assert await queue_due_syncs(factory) == 0  # not enabled yet
    await client.patch(
        f"/api/v1/integrations/{integration['id']}", json={"enabled": True}, headers=owner.headers
    )
    assert await queue_due_syncs(factory) == 1
    assert await queue_due_syncs(factory) == 0  # one is already queued
    assert await process_next_search_sync()
    assert await queue_due_syncs(factory) == 0  # synced recently


async def test_the_assistant_answers_from_search_console(
    client: AsyncClient, fake_google: FakeGoogle, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.ai.grounding import check_output
    from app.modules.ai.outputs import AgentAnswer
    from app.modules.ai.tools import ToolContext
    from app.modules.ai.topics import evidence_for
    from app.modules.projects.models import Project

    owner, org, project = await _org(client)
    integration = (await _integration(client, owner, org)).json()
    await client.post(
        f"/api/v1/integrations/{integration['id']}/search-console/syncs", headers=owner.headers
    )
    assert await process_next_search_sync()
    import uuid

    async with get_session_factory()() as session:
        p = await session.get(Project, uuid.UUID(project["id"]))
        assert p is not None
        found = await evidence_for(ToolContext(session, p), "How many clicks did Google send us?")
        assert found is not None
        search = found["search_performance"]
        assert search["totals"]["clicks"] == 80 and search["totals"]["ctr_percent"] == 3.3
        assert "not_available" not in found  # clicks are covered by the imported data
        visitors = await evidence_for(ToolContext(session, p), "How many visitors did we get?")
        assert visitors is not None and "search_performance" in visitors
        assert visitors["not_available"]["data"] == ["visitor numbers and traffic"]
        # Search Console has no conversions: they stay unavailable when it is connected.
        sales = await evidence_for(ToolContext(session, p), "How many clicks and conversions?")
        assert sales is not None and "search_performance" in sales
        assert sales["not_available"]["data"] == ["conversions and bounce rate"]

    facts = {"search_performance": search}
    grounded = check_output(AgentAnswer(answer="Google Search sent 80 clicks."), facts, set())
    assert grounded.passed, grounded.violations
    invented = check_output(AgentAnswer(answer="Google Search sent 81 clicks."), facts, set())
    assert not invented.passed
    home = search["top_pages"][0]["position"]  # (3 x 1000 + 4 x 900) / 1900 impressions
    assert home == 3.5
    position = check_output(
        AgentAnswer(answer=f"The home page is at position {home}."), facts, set()
    )
    assert position.passed, position.violations
    guessed = check_output(AgentAnswer(answer="You will reach position 1 soon."), facts, set())
    assert not guessed.passed


async def test_no_data_without_search_console(client: AsyncClient) -> None:
    owner, org, project = await _org(client)
    other = await make_project(client, owner, org["id"], "https://lms.example.org")
    for p in (project, other):
        state = (
            await client.get(
                f"/api/v1/projects/{p['id']}/search-performance", headers=owner.headers
            )
        ).json()
        assert state["state"] == "not_connected" and state["top_pages"] == []
    assert date.today()  # figures never default to anything


async def test_records_from_before_the_connection_do_not_count_as_connected(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    """A record saved when integrations were records only: an email typed as the property
    and a password as the credential. It must not be reported as a connection."""
    from app.core import crypto
    from app.modules.integrations.models import Integration

    owner, org, project = await _org(client)
    async with get_session_factory()() as session:
        session.add(
            Integration(
                organisation_id=uuid.UUID(org["id"]),
                provider="google_search_console",
                name="Old record",
                config={"property_url": "dirit@niit.edu.pk"},
                secret=crypto.encrypt("not-a-key"),
                secret_hint="set",
            )
        )
        await session.commit()
    state = (
        await client.get(
            f"/api/v1/projects/{project['id']}/search-performance", headers=owner.headers
        )
    ).json()
    assert state["state"] == "not_connected" and state["properties"] == []


async def test_click_opportunities_compare_with_the_sites_own_rate(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    from types import SimpleNamespace

    from app.modules.ai.tasks import search_queries_for
    from app.modules.ai.tools import ToolContext
    from app.modules.crawler.models import (
        AnalysisStatus,
        CrawlJob,
        CrawlPage,
        CrawlStatus,
        FetchStatus,
    )
    from app.modules.projects.models import Project
    from app.modules.seo.models import Category, SeoIssue, Severity

    def row(path: str, clicks: int, impressions: int, position: float) -> dict[str, Any]:
        return {
            "keys": [_day(2), f"https://example.org{path}"],
            "clicks": clicks,
            "impressions": impressions,
            "position": position,
        }

    fake_google.day_rows = [
        row("/", 100, 1000, 2.0),  # top 3 at 10%
        row("/fees", 8, 400, 2.5),  # top 3 at 2%: below the band's 108 / 1400
        row("/admissions", 25, 500, 6.0),  # positions 4-10 at 5%: above the band
        row("/news", 3, 300, 8.0),  # 1%: below the band's 28 / 850
        row("/small", 0, 50, 5.0),  # too few impressions to list, but in the band
        row("/deep", 2, 2000, 25.0),  # not on the first page
    ]
    fake_google.query_rows = [
        {"keys": ["https://example.org/fees", "example fees"], "clicks": 6, "impressions": 300, "position": 2.0},
        {"keys": ["https://example.org/fees", "example fees 2026"], "clicks": 2, "impressions": 100, "position": 3.0},
    ]  # fmt: skip
    owner, org, project = await _org(client)
    integration = (await _integration(client, owner, org)).json()
    await client.post(
        f"/api/v1/integrations/{integration['id']}/search-console/syncs", headers=owner.headers
    )
    assert await process_next_search_sync()

    project_id, org_id = uuid.UUID(project["id"]), uuid.UUID(org["id"])
    async with get_session_factory()() as session:
        job = CrawlJob(
            organisation_id=org_id,
            project_id=project_id,
            status=CrawlStatus.COMPLETED,
            config={},
            analysis_status=AnalysisStatus.COMPLETED,
        )
        session.add(job)
        await session.flush()
        page = CrawlPage(
            organisation_id=org_id,
            crawl_job_id=job.id,
            url="https://example.org/fees",
            discovered_via="link",
            fetch_status=FetchStatus.FETCHED,
            redirect_chain=[],
            structured_data={},
            title="Fees",
            meta_description="Fee structure.",
        )
        session.add(page)
        now = datetime.now(UTC)
        for rule in ("onpage.title_length", "onpage.meta_description_length", "onpage.h1_missing"):
            session.add(
                SeoIssue(
                    organisation_id=org_id,
                    project_id=project_id,
                    issue_key=f"{rule}:/fees",
                    rule_id=rule,
                    scope="page",
                    category=Category.ON_PAGE,
                    severity=Severity.MEDIUM,
                    title=rule,
                    description="d",
                    recommendation="r",
                    evidence={},
                    affected_url=page.url,
                    affected_urls=[page.url],
                    affected_page_count=1,
                    confidence="high",
                    effort="low",
                    priority_score=1.0,
                    priority_breakdown=[],
                    first_detected_at=now,
                    last_detected_at=now,
                )
            )
        await session.commit()
        page_id = page.id

    perf = (
        await client.get(
            f"/api/v1/projects/{project['id']}/search-performance",
            params={"days": 28},
            headers=owner.headers,
        )
    ).json()
    found = perf["opportunities"]
    assert [o["page"] for o in found] == ["https://example.org/fees", "https://example.org/news"]
    fees, news = found
    assert fees["band"] == "top_3" and fees["band_ctr"] == round(108 / 1400, 4)
    assert fees["ctr"] == 0.02 and fees["position"] == 2.5
    assert fees["page_id"] == str(page_id) and fees["title"] == "Fees"
    assert fees["metadata_issues"] == 2  # title and description issues, not the H1 one
    assert news["band"] == "positions_4_10" and news["band_ctr"] == round(28 / 850, 4)
    assert news["page_id"] is None and news["metadata_issues"] == 0  # not in the crawl

    async with get_session_factory()() as session:
        p = await session.get(Project, project_id)
        assert p is not None
        env = SimpleNamespace(session=session, tools=ToolContext(session, p))
        # A query with a year is left out: drafts take years and fees from the page only.
        assert await search_queries_for(env, "https://example.org/fees") == ["example fees"]  # type: ignore[arg-type]
        assert await search_queries_for(env, "https://example.org/other") == []  # type: ignore[arg-type]


async def test_an_unreadable_stored_key_is_explained(
    client: AsyncClient, fake_google: FakeGoogle
) -> None:
    from app.core import crypto
    from app.modules.integrations.models import Integration

    owner, org, _ = await _org(client)
    integration = (await _integration(client, owner, org)).json()
    async with get_session_factory()() as session:
        row = await session.get(Integration, uuid.UUID(integration["id"]))
        assert row is not None
        row.secret = crypto.encrypt("not a key")  # stored before keys were checked
        await session.commit()
    tested = await client.post(
        f"/api/v1/integrations/{integration['id']}/search-console/test", headers=owner.headers
    )
    assert tested.status_code == 409
    assert tested.json()["error"]["code"] == "credential_unreadable"
