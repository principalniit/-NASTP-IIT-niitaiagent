"""Background worker: claims queued crawl jobs from PostgreSQL and runs them.

    uv run python -m app.worker

Several workers may run at once; `FOR UPDATE SKIP LOCKED` guarantees each job is claimed
by exactly one of them.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  (registers every model so foreign keys resolve)
from app.core.config import get_settings
from app.core.database import dispose_engine, get_session_factory
from app.core.logging import configure_logging
from app.modules.ai.agent import MAX_TOOL_CALLS
from app.modules.ai.models import AIAnalysis, AIStatus
from app.modules.ai.runner import run_analysis
from app.modules.crawler.engine import CrawlEngine
from app.modules.crawler.models import AnalysisStatus, CrawlJob, CrawlStatus
from app.modules.monitoring.retention import apply_retention
from app.modules.monitoring.service import process_due_schedules
from app.modules.reports.models import PdfStatus, Report, ReportStatus
from app.modules.reports.service import run_report
from app.modules.seo.analysis import AnalysisError, analyse_crawl

logger = logging.getLogger("app.worker")

CLAIM_SQL = text(
    """
    UPDATE crawl_jobs SET status = 'running', worker_id = :worker, started_at = now(),
           heartbeat_at = now(), updated_at = now()
    WHERE id = (
        SELECT id FROM crawl_jobs WHERE status = 'queued'
        ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)


CLAIM_ANALYSIS_SQL = text(
    """
    UPDATE crawl_jobs SET analysis_status = 'running', updated_at = now()
    WHERE id = (
        SELECT id FROM crawl_jobs WHERE analysis_status = 'queued'
        ORDER BY finished_at LIMIT 1 FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)


CLAIM_AI_SQL = text(
    """
    UPDATE ai_analyses SET status = 'running', started_at = now()
    WHERE id = (
        SELECT id FROM ai_analyses WHERE status = 'queued'
        ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)


# A question may need up to (MAX_TOOL_CALLS + 3) model calls of two attempts each, each
# bounded by AI_TIMEOUT_SECONDS; allow that plus a margin before calling a task stale.
AI_STALE_TIMEOUTS = 2 * (MAX_TOOL_CALLS + 3) + 2


CLAIM_REPORT_SQL = text(
    """
    UPDATE reports SET status = 'running', started_at = now()
    WHERE id = (
        SELECT id FROM reports WHERE status = 'queued'
        ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)
REPORT_STALE_SECONDS = 1800
RETENTION_INTERVAL_SECONDS = 3600


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


async def claim_next_job(
    factory: async_sessionmaker[AsyncSession], worker_id: str
) -> uuid.UUID | None:
    async with factory() as session:
        job_id: uuid.UUID | None = await session.scalar(CLAIM_SQL, {"worker": worker_id})
        await session.commit()
        return job_id


async def recover_stale_jobs(factory: async_sessionmaker[AsyncSession], stale_seconds: int) -> int:
    """Fail running crawls whose worker stopped sending heartbeats, and analyses whose
    worker stopped before finishing."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_seconds)
    ai_cutoff = datetime.now(UTC) - timedelta(
        seconds=get_settings().ai_timeout_seconds * AI_STALE_TIMEOUTS
    )
    async with factory() as session:
        await session.execute(
            update(AIAnalysis)
            .where(AIAnalysis.status == AIStatus.RUNNING, AIAnalysis.started_at < ai_cutoff)
            .values(
                status=AIStatus.FAILED,
                error="The worker running this AI task stopped unexpectedly.",
                finished_at=datetime.now(UTC),
            )
        )
        await session.execute(
            update(Report)
            .where(
                Report.status == ReportStatus.RUNNING,
                Report.started_at < datetime.now(UTC) - timedelta(seconds=REPORT_STALE_SECONDS),
            )
            .values(
                status=ReportStatus.FAILED,
                pdf_status=PdfStatus.FAILED,
                error="The worker generating this report stopped unexpectedly.",
                finished_at=datetime.now(UTC),
            )
        )
        await session.execute(
            update(CrawlJob)
            .where(
                CrawlJob.analysis_status == AnalysisStatus.RUNNING,
                CrawlJob.updated_at < cutoff,
            )
            .values(
                analysis_status=AnalysisStatus.FAILED,
                analysis_error="The worker running this analysis stopped unexpectedly.",
            )
        )
        result = await session.execute(
            update(CrawlJob)
            .where(
                CrawlJob.status.in_([CrawlStatus.RUNNING, CrawlStatus.CANCELLING]),
                CrawlJob.heartbeat_at < cutoff,
            )
            .values(
                status=CrawlStatus.FAILED,
                error_message="The worker running this crawl stopped unexpectedly.",
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


async def _mark_failed(factory: async_sessionmaker[AsyncSession], job_id: uuid.UUID) -> None:
    async with factory() as session:
        job = await session.get(CrawlJob, job_id)
        if job is not None:
            job.status = CrawlStatus.FAILED
            job.error_message = "The crawl failed because of an internal error. See worker logs."
            job.finished_at = datetime.now(UTC)
            await session.commit()


async def process_next_job(
    worker_id: str,
    *,
    factory: async_sessionmaker[AsyncSession] | None = None,
    engine_factory: Callable[[uuid.UUID], CrawlEngine] | None = None,
) -> bool:
    """Claim and run one job. Returns False when the queue was empty."""
    factory = factory or get_session_factory()
    job_id = await claim_next_job(factory, worker_id)
    if job_id is None:
        return False
    logger.info("Crawl started", extra={"crawl_job_id": str(job_id)})
    engine = (
        engine_factory(job_id) if engine_factory else CrawlEngine(job_id, session_factory=factory)
    )
    try:
        status = await engine.run()
        logger.info("Crawl finished", extra={"crawl_job_id": str(job_id), "status": status.value})
    except Exception:
        logger.exception("Crawl failed", extra={"crawl_job_id": str(job_id)})
        await _mark_failed(factory, job_id)
    return True


async def process_next_analysis(*, factory: async_sessionmaker[AsyncSession] | None = None) -> bool:
    """Claim and run one queued analysis. Returns False when none was queued."""
    factory = factory or get_session_factory()
    async with factory() as session:
        job_id: uuid.UUID | None = await session.scalar(CLAIM_ANALYSIS_SQL)
        await session.commit()
    if job_id is None:
        return False
    try:
        await analyse_crawl(job_id, factory=factory)
    except Exception as exc:
        if isinstance(exc, AnalysisError):
            message = str(exc)
        else:
            logger.exception("Analysis failed", extra={"crawl_job_id": str(job_id)})
            message = "The analysis failed because of an internal error. See worker logs."
        async with factory() as session:
            job = await session.get(CrawlJob, job_id)
            if job is not None:
                job.analysis_status = AnalysisStatus.FAILED
                job.analysis_error = message
                await session.commit()
    return True


async def process_next_ai_task(*, factory: async_sessionmaker[AsyncSession] | None = None) -> bool:
    """Claim and run one queued AI analysis. Returns False when none was queued."""
    factory = factory or get_session_factory()
    async with factory() as session:
        analysis_id: uuid.UUID | None = await session.scalar(CLAIM_AI_SQL)
        await session.commit()
    if analysis_id is None:
        return False
    try:
        await run_analysis(analysis_id, factory=factory)
    except Exception:
        logger.exception("AI analysis failed", extra={"ai_analysis_id": str(analysis_id)})
        async with factory() as session:
            analysis = await session.get(AIAnalysis, analysis_id)
            if analysis is not None:
                analysis.status = AIStatus.FAILED
                analysis.error = "The AI task failed because of an internal error. See worker logs."
                analysis.finished_at = datetime.now(UTC)
                await session.commit()
    return True


async def process_next_report(*, factory: async_sessionmaker[AsyncSession] | None = None) -> bool:
    """Claim and generate one queued report. Returns False when none was queued."""
    factory = factory or get_session_factory()
    async with factory() as session:
        report_id: uuid.UUID | None = await session.scalar(CLAIM_REPORT_SQL)
        await session.commit()
    if report_id is None:
        return False
    try:
        await run_report(report_id, factory=factory)
    except Exception:
        logger.exception("Report generation failed", extra={"report_id": str(report_id)})
        async with factory() as session:
            report = await session.get(Report, report_id)
            if report is not None:
                report.status = ReportStatus.FAILED
                report.pdf_status = PdfStatus.FAILED
                report.error = "The report failed because of an internal error. See worker logs."
                report.finished_at = datetime.now(UTC)
                await session.commit()
    return True


async def run_worker(stop: asyncio.Event) -> None:
    settings = get_settings()
    worker_id = worker_identity()
    factory = get_session_factory()
    logger.info("Worker started", extra={"worker_id": worker_id})
    recovered = await recover_stale_jobs(factory, settings.worker_stale_after_seconds)
    if recovered:
        logger.warning("Marked abandoned crawls as failed", extra={"count": recovered})
    last_recovery = asyncio.get_running_loop().time()
    last_retention = 0.0
    while not stop.is_set():
        try:
            worked = await process_next_job(worker_id, factory=factory)
            worked = await process_next_analysis(factory=factory) or worked
            worked = await process_next_ai_task(factory=factory) or worked
            worked = await process_next_report(factory=factory) or worked
        except Exception:
            logger.exception("Worker loop error")
            worked = False
        now = asyncio.get_running_loop().time()
        if now - last_recovery > 60:
            await recover_stale_jobs(factory, settings.worker_stale_after_seconds)
            try:
                if await process_due_schedules(factory):
                    worked = True
            except Exception:
                logger.exception("Scheduled crawl check failed")
            if now - last_retention > RETENTION_INTERVAL_SECONDS:
                try:
                    await apply_retention(factory)
                except Exception:
                    logger.exception("Data retention failed")
                last_retention = now
            last_recovery = now
        if not worked:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
    logger.info("Worker stopped", extra={"worker_id": worker_id})


def main() -> None:
    configure_logging(get_settings().log_level)

    async def runner() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):  # not supported on Windows
                loop.add_signal_handler(sig, stop.set)
        try:
            await run_worker(stop)
        finally:
            await dispose_engine()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
