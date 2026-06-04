from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone

from graph.backends.base import AbstractGraphBackend
from scraper.jobs.crawler import AccountCrawler, CrawlerConfig

logger = logging.getLogger(__name__)


def _make_loop() -> asyncio.AbstractEventLoop:
    """Return a subprocess-capable event loop for the crawl thread.

    Playwright launches the browser by spawning a subprocess. On Windows that
    requires a ``ProactorEventLoop`` — but uvicorn runs its request loop on a
    ``SelectorEventLoop`` when started with ``--reload`` (or ``--workers``),
    and Selector loops raise ``NotImplementedError`` on subprocess spawn. We
    therefore run each crawl in its own thread with a private Proactor loop;
    this behaves identically whether or not the server uses ``--reload``, and
    on every platform.

    ``set_event_loop`` is thread-local, so this never touches the server loop.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


async def _crawl(
    config: CrawlerConfig,
    graph: AbstractGraphBackend,
    job_id: uuid.UUID,
) -> None:
    # A SQLAlchemy async engine is bound to the event loop that created it, so
    # the crawl thread needs its own engine/session factory — it cannot reuse
    # the server's. Both point at the same database (SQLite uses WAL, so the
    # API keeps reading while the crawl writes). The graph backend is the
    # shared in-memory instance so crawl results show up in the API.
    from config.settings import get_settings
    from storage.engine import create_engine_from_settings
    from storage.session import create_session_factory

    engine = create_engine_from_settings(get_settings())
    try:
        session_factory = create_session_factory(engine)
        crawler = AccountCrawler(config=config, session_factory=session_factory, graph=graph)
        await crawler.run(job_id=job_id)
    except Exception:
        logger.exception("Crawl job %s crashed in worker thread", job_id)
        await _mark_failed(engine, job_id)
    finally:
        await engine.dispose()


async def _mark_failed(engine: object, job_id: uuid.UUID) -> None:
    """Best-effort: flip a job to FAILED if the crawl died before finalizing.

    ``AccountCrawler.run`` finalizes the job itself on normal completion and on
    most failures; this only covers the rare case where an error escapes it
    (e.g. engine setup), so the UI never hangs on RUNNING forever.
    """
    try:
        from storage.models.job import JobStatus
        from storage.repositories.job_repo import JobRepository
        from storage.session import create_session_factory

        session_factory = create_session_factory(engine)  # type: ignore[arg-type]
        async with session_factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job(job_id)
            if job is not None and job.status in (JobStatus.RUNNING, JobStatus.PENDING):
                await repo.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    completed_at=datetime.now(timezone.utc),
                    error_message="crawl crashed before completion",
                )
                await session.commit()
    except Exception:
        logger.exception("Could not mark job %s as failed", job_id)


def run_crawl_in_thread(
    config: CrawlerConfig,
    graph: AbstractGraphBackend,
    job_id: uuid.UUID,
) -> None:
    """Thread target: run a crawl on a private, subprocess-capable event loop."""
    loop = _make_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_crawl(config, graph, job_id))
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)
