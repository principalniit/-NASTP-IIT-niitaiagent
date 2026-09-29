"""Management reports: generation in the worker, the 13 sections, escaping, PDF export,
branding, AI on and off, permissions and limits."""

import copy
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.ai.models import AIAnalysis, AIKind, AIStatus
from app.modules.crawler.models import CrawlJob
from app.modules.reports import render
from app.modules.reports.models import Report
from app.worker import process_next_report, recover_stale_jobs
from tests.conftest import TestUser, add_member, make_user
from tests.fixtures.site import FixtureSite, build_standard_site
from tests.integration.test_ai_api import analysed

SECTIONS = [
    "Executive summary",
    "Overall SEO health",
    "Crawl overview",
    "Critical issues",
    "High-priority issues",
    "Technical SEO",
    "On-page SEO",
    "Content quality",
    "Internal linking",
    "Structured data",
    "AI recommendations",
    "Recommended action plan",
    "Methodology and limitations",
]


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


@pytest.fixture(autouse=True)
def pdf_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a locally installed Chromium when the environment names one."""
    path = os.environ.get("TEST_PDF_BROWSER_PATH", "")
    monkeypatch.setattr(get_settings(), "report_pdf_browser_path", path)


async def generate(client: AsyncClient, user: TestUser, project_id: str, **body: object) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"/api/v1/projects/{project_id}/reports", json=body, headers=user.headers
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    assert await process_next_report()
    report = await client.get(f"/api/v1/reports/{response.json()['id']}", headers=user.headers)
    return report.json()  # type: ignore[no-any-return]


async def html_of(client: AsyncClient, user: TestUser, report_id: str) -> str:
    response = await client.get(f"/api/v1/reports/{report_id}/html", headers=user.headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    return response.text


async def test_report_has_every_section_with_evidence(
    client: AsyncClient, site: FixtureSite
) -> None:
    owner, _, project = await analysed(client, site)
    report = await generate(client, owner, project["id"])
    assert report["status"] == "completed", report["error"]
    assert report["title"] == "SEO health report: Site"
    html = await html_of(client, owner, report["id"])

    positions = [html.index(f"{n}.</span>{title}") for n, title in enumerate(SECTIONS, 1)]
    assert positions == sorted(positions)
    assert "Pages analysed" in html and "Crawl completed" in html
    assert "/missing" in html and "404" in html  # evidence and affected URLs
    assert "Recommendation:" in html
    assert "not a search ranking" in html
    assert "No AI summary was generated for this crawl" in html
    assert "<script" not in html.lower()
    assert "default-src 'none'" in html  # the document forbids scripts and remote loads

    async with get_session_factory()() as session:
        stored = await session.get(Report, uuid.UUID(report["id"]))
        assert stored is not None
        data = stored.data
    summary = " ".join(data["executive_summary"])
    assert f"It analysed {data['meta']['pages_analysed']} pages" in summary
    assert "site-health score" in summary
    assert data["action_plan"]["fix_first"], "high-severity issues lead the plan"
    assert data["counts"]["open_total"] > 0

    # Crawled text is untrusted: everything is escaped when rendered.
    hostile = copy.deepcopy(data)
    hostile["critical"]["issues"] = [
        {
            **data["high"]["issues"][0],
            "title": "<script>alert(1)</script>",
            "affected_urls": ["https://x/<img src=x onerror=alert(1)>"],
        }
    ]
    hostile["critical"]["total"] = 1
    rendered = render.render_html(hostile, None)
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<img src=x" not in rendered


async def test_ai_content_is_labelled_and_optional(client: AsyncClient, site: FixtureSite) -> None:
    owner, org, project = await analysed(client, site)
    async with get_session_factory()() as session:
        crawl = await session.scalar(
            select(CrawlJob).where(CrawlJob.project_id == uuid.UUID(project["id"]))
        )
        assert crawl is not None
        session.add(
            AIAnalysis(
                organisation_id=uuid.UUID(org["id"]),
                project_id=uuid.UUID(project["id"]),
                crawl_job_id=crawl.id,
                kind=AIKind.MANAGEMENT_SUMMARY,
                status=AIStatus.COMPLETED,
                subject_type="project",
                model="llama3.1:8b",
                output={
                    "headline": "Fix broken pages first",
                    "overview": "Two pages return errors.",
                    "key_findings": [],
                    "priorities": [{"action": "Repair /missing", "reason": "It returns 404."}],
                },
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()

    with_ai = await html_of(client, owner, (await generate(client, owner, project["id"]))["id"])
    assert "Fix broken pages first" in with_ai and "Written by an AI model (llama3.1:8b)" in with_ai
    without = await generate(client, owner, project["id"], include_ai=False, title="Board pack")
    assert without["title"] == "Board pack" and without["include_ai"] is False
    html = await html_of(client, owner, without["id"])
    assert "Fix broken pages first" not in html
    assert "AI-generated content was not included in this report" in html
    assert "Executive summary" in html  # the rule-written summary never needs AI


async def test_branding_and_logo(
    client: AsyncClient, site: FixtureSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org, project = await analysed(client, site)
    response = await client.patch(
        f"/api/v1/organisations/{org['id']}",
        json={
            "logo_url": "https://logo.example.org/logo.png",
            "settings": {
                "report_branding": {"primary_colour": "#0a7f5a", "footer_text": "NIIT internal"}
            },
        },
        headers=owner.headers,
    )
    assert response.status_code == 200, response.text

    async def fake_logo(url: str | None) -> str | None:
        assert url == "https://logo.example.org/logo.png"
        return "data:image/png;base64,iVBORw0KGgo="

    monkeypatch.setattr(render, "fetch_logo", fake_logo)
    html = await html_of(client, owner, (await generate(client, owner, project["id"]))["id"])
    assert "--brand: #0a7f5a" in html and "NIIT internal" in html
    assert 'src="data:image/png;base64,iVBORw0KGgo="' in html


async def test_logo_fetch_uses_the_ssrf_guard() -> None:
    assert await render.fetch_logo("https://127.0.0.1/logo.png") is None
    assert await render.fetch_logo("https://169.254.169.254/latest") is None
    assert await render.fetch_logo("http://example.org/logo.png") is None  # HTTPS only
    assert await render.fetch_logo(None) is None


async def test_pdf_export(
    client: AsyncClient, site: FixtureSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _, project = await analysed(client, site)
    monkeypatch.setattr(get_settings(), "report_pdf_browser_path", "/nonexistent/chrome")
    missing = await generate(client, owner, project["id"])
    assert missing["status"] == "completed" and missing["pdf_status"] == "unavailable"
    assert "playwright install chromium" in missing["pdf_error"]
    refused = await client.get(f"/api/v1/reports/{missing['id']}/pdf", headers=owner.headers)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "pdf_not_ready"
    await html_of(client, owner, missing["id"])  # the HTML report still works

    browser = os.environ.get("TEST_PDF_BROWSER_PATH", "")
    monkeypatch.setattr(get_settings(), "report_pdf_browser_path", browser)
    report = await generate(client, owner, project["id"])
    if report["pdf_status"] == "unavailable":
        pytest.skip("No Chromium for PDF rendering here (set TEST_PDF_BROWSER_PATH)")
    assert report["pdf_status"] == "ready", report["pdf_error"]
    pdf = await client.get(f"/api/v1/reports/{report['id']}/pdf", headers=owner.headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 5000
    assert "attachment" in pdf.headers["content-disposition"]


async def test_permissions_limits_and_lifecycle(
    client: AsyncClient, site: FixtureSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org, project = await analysed(client, site)
    url = f"/api/v1/projects/{project['id']}/reports"
    viewer = await make_user(client, "viewer@example.org")
    editor = await make_user(client, "editor@example.org")
    manager = await make_user(client, "manager@example.org")
    for user, role in ((viewer, "viewer"), (editor, "editor"), (manager, "seo_manager")):
        await add_member(client, owner, org["id"], user, role)

    assert (await client.post(url, json={}, headers=viewer.headers)).status_code == 403
    assert (await client.post(url, json={}, headers=editor.headers)).status_code == 403
    assert (
        await client.post(url, json={"unexpected": 1}, headers=owner.headers)
    ).status_code == 422
    report = await generate(client, manager, project["id"])
    assert (await client.get(url, headers=viewer.headers)).json()["total"] == 1
    await html_of(client, viewer, report["id"])
    assert (
        await client.delete(f"/api/v1/reports/{report['id']}", headers=viewer.headers)
    ).status_code == 403

    queued = []
    for _ in range(3):
        response = await client.post(url, json={}, headers=owner.headers)
        assert response.status_code == 202
        queued.append(response.json()["id"])
    assert (await client.post(url, json={}, headers=owner.headers)).status_code == 429
    not_ready = await client.get(f"/api/v1/reports/{queued[0]}/html", headers=owner.headers)
    assert not_ready.status_code == 409 and not_ready.json()["error"]["code"] == "not_ready"
    busy = await client.delete(f"/api/v1/reports/{queued[0]}", headers=owner.headers)
    assert busy.status_code == 409

    deleted = await client.delete(f"/api/v1/reports/{report['id']}", headers=owner.headers)
    assert deleted.status_code == 204
    assert (
        await client.get(f"/api/v1/reports/{report['id']}", headers=owner.headers)
    ).status_code == 404
    audit = (
        await client.get(
            f"/api/v1/organisations/{org['id']}/audit-logs",
            params={"page_size": 100},
            headers=owner.headers,
        )
    ).json()
    assert {"report.requested", "report.deleted"} <= {e["action"] for e in audit["items"]}

    # A worker that dies mid-report leaves it failed, not stuck.
    async with get_session_factory()() as session:
        stuck = await session.get(Report, uuid.UUID(queued[0]))
        assert stuck is not None
        stuck.status, stuck.started_at = "running", datetime.now(UTC) - timedelta(hours=2)  # type: ignore[assignment]
        await session.commit()
    await recover_stale_jobs(get_session_factory(), 300)
    failed = (await client.get(f"/api/v1/reports/{queued[0]}", headers=owner.headers)).json()
    assert failed["status"] == "failed" and "stopped unexpectedly" in failed["error"]


async def test_reports_need_an_analysed_crawl(client: AsyncClient, site: FixtureSite) -> None:
    from tests.integration.test_crawl_api import setup

    owner, _, project = await setup(client, site)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/reports", json={}, headers=owner.headers
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_analysed"
    assert not await process_next_report()
