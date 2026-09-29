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
from app.modules.crawler.engine import CrawlEngine
from app.modules.crawler.models import CrawlJob, CrawlStatus

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
    """Fail running crawls whose worker stopped sending heartbeats."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_seconds)
    async with factory() as session:
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


async def run_worker(stop: asyncio.Event) -> None:
    settings = get_settings()
    worker_id = worker_identity()
    factory = get_session_factory()
    logger.info("Worker started", extra={"worker_id": worker_id})
    recovered = await recover_stale_jobs(factory, settings.worker_stale_after_seconds)
    if recovered:
        logger.warning("Marked abandoned crawls as failed", extra={"count": recovered})
    last_recovery = asyncio.get_running_loop().time()
    while not stop.is_set():
        try:
            worked = await process_next_job(worker_id, factory=factory)
        except Exception:
            logger.exception("Worker loop error")
            worked = False
        now = asyncio.get_running_loop().time()
        if now - last_recovery > 60:
            await recover_stale_jobs(factory, settings.worker_stale_after_seconds)
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
