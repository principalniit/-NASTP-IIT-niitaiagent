"""Findings from the Phase 6 security review: logo fetch, retention, integrations."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlPage, CrawlStatus
from app.modules.monitoring.retention import apply_retention
from app.modules.organisations.models import Organisation
from app.modules.reports import render
from tests.conftest import add_member, make_org, make_user
from tests.integration.conftest import project  # noqa: F401  (fixture)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def _stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _serve(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(render, "GuardedTransport", lambda policy: httpx.MockTransport(handler))


async def test_a_slow_logo_server_cannot_hold_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def trickle() -> AsyncIterator[bytes]:
        for _ in range(1000):
            await asyncio.sleep(0.1)
            yield b"\x00"

    _serve(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"content-type": "image/png"}, content=trickle()
        ),
    )
    monkeypatch.setattr(render, "LOGO_TOTAL_SECONDS", 0.5)
    started = time.monotonic()
    assert await render.fetch_logo("https://logo.example.org/logo.png") is None
    assert time.monotonic() - started < 3


async def test_logo_must_be_uncompressed_and_a_real_image(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("accept-encoding", ""))
        path = request.url.path
        if path == "/gzip.png":
            return httpx.Response(
                200,
                headers={"content-type": "image/png", "content-encoding": "gzip"},
                content=_stream(b"x"),
            )
        if path == "/html.png":
            return httpx.Response(
                200, headers={"content-type": "image/png"}, content=_stream(b"<svg/>")
            )
        return httpx.Response(200, headers={"content-type": "image/png"}, content=_stream(PNG))

    _serve(monkeypatch, handler)
    assert await render.fetch_logo("https://logo.example.org/gzip.png") is None
    assert await render.fetch_logo("https://logo.example.org/html.png") is None
    good = await render.fetch_logo("https://logo.example.org/logo.png")
    assert good is not None and good.startswith("data:image/png;base64,")
    assert set(seen) == {"identity"}


async def _history(org_id: uuid.UUID, project_id: uuid.UUID, statuses: list) -> list[uuid.UUID]:  # type: ignore[type-arg]
    """Crawls oldest first, each with one page. `statuses` holds (crawl, analysis) pairs."""
    ids = []
    async with get_session_factory()() as session:
        for n, (status, analysis) in enumerate(statuses):
            job = CrawlJob(
                organisation_id=org_id,
                project_id=project_id,
                status=status,
                config={},
                analysis_status=analysis,
                created_at=datetime.now(UTC) - timedelta(days=len(statuses) - n),
            )
            session.add(job)
            await session.flush()
            session.add(
                CrawlPage(
                    organisation_id=org_id,
                    crawl_job_id=job.id,
                    url="http://x/",
                    discovered_via="link",
                    fetch_status="fetched",
                    redirect_chain=[],
                    structured_data={},
                )
            )
            ids.append(job.id)
        org = await session.get(Organisation, org_id)
        assert org is not None
        org.settings = {**org.settings, "data_retention": {"keep_crawls": 2}}
        await session.commit()
    return ids


async def _pruned(crawl_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        job = await session.get(CrawlJob, crawl_id)
        return job is not None and job.pages_pruned_at is not None


async def test_cancelled_crawls_cannot_push_data_out(project) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    org_id, project_id = project
    done, cancel = (
        (CrawlStatus.COMPLETED, AnalysisStatus.NONE),
        (
            CrawlStatus.CANCELLED,
            AnalysisStatus.NONE,
        ),
    )
    failed_analysis = (CrawlStatus.COMPLETED, AnalysisStatus.FAILED)
    running = (CrawlStatus.COMPLETED, AnalysisStatus.RUNNING)
    old, busy, kept, _, _ = await _history(
        org_id, project_id, [done, running, failed_analysis, cancel, cancel]
    )
    await apply_retention()
    assert not await _pruned(kept)  # newest completed crawl: cancellations do not count
    assert not await _pruned(busy)  # its analysis is running
    assert await _pruned(old)


async def test_a_pruned_crawl_cannot_be_analysed(client: AsyncClient, project) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    org_id, project_id = project
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    await add_member(client, admin, str(org_id), admin, "owner")
    (crawl,) = await _history(org_id, project_id, [(CrawlStatus.COMPLETED, AnalysisStatus.NONE)])
    async with get_session_factory()() as session:
        job = await session.get(CrawlJob, crawl)
        assert job is not None
        job.pages_pruned_at = datetime.now(UTC)
        await session.commit()
    refused = await client.post(f"/api/v1/crawls/{crawl}/analyse", headers=admin.headers)
    assert refused.status_code == 409 and "retention" in refused.json()["error"]["message"]


async def test_platform_admins_do_not_see_integrations_of_other_organisations(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        get_settings(), "integrations_encryption_keys", SecretStr(Fernet.generate_key().decode())
    )
    creator = await make_user(client, "creator@example.org", platform_admin=True)
    org = await make_org(client, creator, "Org")
    base = f"/api/v1/organisations/{org['id']}/integrations"
    made = await client.post(
        base,
        json={
            "provider": "webhook",
            "name": "Hook",
            "config": {"url": "https://hooks.example.org/x"},
            "secret": "short-pass-1",
        },
        headers=creator.headers,
    )
    assert made.status_code == 201 and made.json()["secret_hint"] == "set"  # short: no characters
    outsider = await make_user(client, "outsider@example.org", platform_admin=True)
    assert (await client.get(base, headers=outsider.headers)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/integrations/{made.json()['id']}",
            json={"enabled": True},
            headers=outsider.headers,
        )
    ).status_code == 404
