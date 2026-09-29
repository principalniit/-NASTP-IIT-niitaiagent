"""SEO engine end to end: crawl the fixture site, analyse, and track issues across crawls."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, update

from app.core.database import get_session_factory
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlStatus
from app.modules.seo.analysis import AnalysisError, analyse_crawl
from app.modules.seo.models import (
    InternalLinkRecommendation,
    ResolutionStatus,
    SchemaFinding,
    SeoIssue,
    SeoScore,
)
from app.worker import process_next_analysis
from tests.fixtures.site import FixtureSite, Response, build_standard_site
from tests.integration.test_crawl_engine import run_crawl


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    with FixtureSite() as s:
        build_standard_site(s)
        yield s


async def issues(project_id: uuid.UUID) -> dict[str, SeoIssue]:
    async with get_session_factory()() as session:
        rows = await session.scalars(select(SeoIssue).where(SeoIssue.project_id == project_id))
        return {f"{i.rule_id} {(i.affected_url or '').rsplit(':', 1)[-1]}": i for i in rows}


def find(found: dict[str, SeoIssue], rule: str, path: str | None = None) -> SeoIssue:
    for issue in found.values():
        if issue.rule_id == rule and (path is None or (issue.affected_url or "").endswith(path)):
            return issue
    raise AssertionError(f"{rule} {path} not found in {sorted(found)}")


async def test_analysis_produces_evidence_based_issues_and_score(
    site: FixtureSite, project
) -> None:  # type: ignore[no-untyped-def]
    job, _ = await run_crawl(site, project)
    assert job.analysis_status == AnalysisStatus.QUEUED  # queued automatically on completion
    await analyse_crawl(job.id)
    found = await issues(project[1])

    missing = find(found, "tech.http_client_error", "/missing")
    assert missing.evidence["status_code"] == 404
    assert missing.recommendation and missing.resolution_status == ResolutionStatus.OPEN
    assert missing.priority_breakdown and 0 < missing.priority_score <= 100
    assert find(found, "tech.http_server_error", "/error").evidence["status_code"] == 500
    assert find(found, "tech.internal_link_to_redirect", "/old-page")
    assert find(found, "tech.unexpected_noindex", "/admissions")
    assert find(found, "links.orphan", "/orphan")
    assert find(found, "tech.blocked_by_robots", "/private/secret")
    assert find(found, "content.duplicate").affected_page_count == 2
    assert find(found, "onpage.image_alt_missing", "/").evidence["images_without_alt"] == 1
    assert find(found, "schema.home_organisation_missing", "/")
    assert all(i.evidence and i.recommendation for i in found.values())
    assert all(i.organisation_id == job.organisation_id for i in found.values())

    async with get_session_factory()() as session:
        score = await session.scalar(select(SeoScore).where(SeoScore.crawl_job_id == job.id))
        assert score is not None and score.overall is not None and 0 <= score.overall < 100
        assert set(score.breakdown["categories"]) == {
            "technical",
            "on_page",
            "content",
            "internal_linking",
            "structured_data",
        }
        recs = list(
            await session.scalars(
                select(InternalLinkRecommendation).where(
                    InternalLinkRecommendation.crawl_job_id == job.id
                )
            )
        )
        assert [
            (
                r.evidence["source_url"].rsplit(":", 1)[-1],
                r.evidence["target_url"].rsplit(":", 1)[-1],
            )
            for r in recs
        ] == [(f"{site.port}/", f"{site.port}/orphan")]
        schema = list(
            await session.scalars(select(SchemaFinding).where(SchemaFinding.crawl_job_id == job.id))
        )
        assert schema == []  # the fixture site has no structured data
        refreshed = await session.get(CrawlJob, job.id)
        assert refreshed is not None and refreshed.analysis_status == AnalysisStatus.COMPLETED

    # Re-running the analysis is idempotent.
    await analyse_crawl(job.id)
    assert set(await issues(project[1])) == set(found)


async def test_issue_lifecycle_across_crawls(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    first, _ = await run_crawl(site, project)
    await analyse_crawl(first.id)
    issue = find(await issues(project[1]), "tech.http_client_error", "/missing")
    error_issue = find(await issues(project[1]), "tech.http_server_error", "/error")
    async with get_session_factory()() as session:
        await session.execute(
            update(SeoIssue)
            .where(SeoIssue.id == error_issue.id)
            .values(resolution_status=ResolutionStatus.IGNORED)
        )
        await session.commit()

    # Fix /missing: the next crawl verifies it, so the issue is resolved.
    site.page("/missing", "Now present", "<h1>Present</h1><p>Restored page</p>")
    second, _ = await run_crawl(site, project)
    await analyse_crawl(second.id)
    found = await issues(project[1])
    resolved = found[next(k for k, v in found.items() if v.id == issue.id)]
    assert resolved.resolution_status == ResolutionStatus.RESOLVED
    assert resolved.resolved_in_crawl_id == second.id
    assert resolved.first_crawl_id == first.id
    # Still failing and ignored by a user: stays ignored.
    assert (
        found[next(k for k, v in found.items() if v.id == error_issue.id)].resolution_status
        == ResolutionStatus.IGNORED
    )

    # Break it again: the same issue reopens and records the recurrence.
    site.routes["/missing"] = Response(404, b"gone", {"Content-Type": "text/html"})
    third, _ = await run_crawl(site, project)
    await analyse_crawl(third.id)
    reopened = find(await issues(project[1]), "tech.http_client_error", "/missing")
    assert reopened.id == issue.id
    assert reopened.resolution_status == ResolutionStatus.OPEN
    assert reopened.recurrence_count == 1


async def test_issues_on_pages_not_recrawled_stay_open(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    first, _ = await run_crawl(site, project)
    await analyse_crawl(first.id)
    deep = find(await issues(project[1]), "tech.http_client_error", "/missing")
    # A small crawl that never reaches /missing cannot verify a fix.
    second, pages = await run_crawl(site, project, max_pages=2)
    assert "/missing" not in pages
    await analyse_crawl(second.id)
    still = find(await issues(project[1]), "tech.http_client_error", "/missing")
    assert still.id == deep.id and still.resolution_status == ResolutionStatus.OPEN


async def test_older_and_unfinished_crawls_cannot_be_analysed(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    first, _ = await run_crawl(site, project)
    second, _ = await run_crawl(site, project)
    await analyse_crawl(second.id)
    with pytest.raises(AnalysisError, match="newer crawl"):
        await analyse_crawl(first.id)
    async with get_session_factory()() as session:
        await session.execute(
            update(CrawlJob).where(CrawlJob.id == first.id).values(status=CrawlStatus.CANCELLED)
        )
        await session.commit()
    with pytest.raises(AnalysisError, match="completed"):
        await analyse_crawl(first.id)


async def test_worker_runs_queued_analysis(site: FixtureSite, project) -> None:  # type: ignore[no-untyped-def]
    job, _ = await run_crawl(site, project)
    assert await process_next_analysis()
    assert not await process_next_analysis()
    async with get_session_factory()() as session:
        refreshed = await session.get(CrawlJob, job.id)
        assert refreshed is not None and refreshed.analysis_status == AnalysisStatus.COMPLETED
