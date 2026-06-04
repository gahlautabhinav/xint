from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, DbSession, GraphBackend
from api.schemas.jobs import (
    JobCreate,
    JobEventResponse,
    JobEventsResponse,
    JobListResponse,
    JobResponse,
)
from scraper.jobs.crawler import CrawlerConfig
from scraper.jobs.runner import run_crawl_in_thread
from storage.models.job import JobStatus
from storage.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def create_job(
    body: JobCreate,
    _key: ApiKeyCheck,
    session: DbSession,
    graph: GraphBackend,
) -> JobResponse:
    """Start a crawl job. Returns 202 with the real job immediately; the crawl
    runs in a dedicated worker thread (its own Proactor event loop) so Playwright
    can spawn the browser subprocess even when the server runs under ``--reload``.
    """
    config = CrawlerConfig(
        seed_username=body.seed_username,
        max_depth=body.max_depth,
        max_accounts=body.max_accounts,
        rate_profile_name=body.rate_profile,  # type: ignore[arg-type]
        proxy_urls=body.proxy_urls,
    )

    # Create the job row up front so we can return its real id (no synthetic
    # placeholder that 404s when the client navigates to it). Capture id +
    # response *before* committing, because commit expires ORM attributes.
    job_repo = JobRepository(session)
    job = await job_repo.create_job(
        seed_username=body.seed_username,
        max_depth=body.max_depth,
        max_accounts=body.max_accounts,
        status=JobStatus.PENDING,
    )
    # Load server-side defaults (created_at) so model_validate doesn't trigger
    # an async lazy-load on an expired attribute.
    await session.refresh(job)
    job_response = JobResponse.model_validate(job)
    job_id = job.id
    await session.commit()  # persist before the worker thread reads the row

    threading.Thread(
        target=run_crawl_in_thread,
        args=(config, graph, job_id),
        name=f"crawl-{body.seed_username}",
        daemon=True,
    ).start()

    return job_response


@router.get("", response_model=JobListResponse)
async def list_jobs(
    _key: ApiKeyCheck,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    job_repo = JobRepository(session)
    jobs = await job_repo.list_jobs(limit=limit, offset=offset)
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    _key: ApiKeyCheck,
    session: DbSession,
) -> JobResponse:
    job_repo = JobRepository(session)
    job = await job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse.model_validate(job)


@router.get("/{job_id}/events", response_model=JobEventsResponse)
async def get_job_events(
    job_id: uuid.UUID,
    _key: ApiKeyCheck,
    session: DbSession,
    since: int = Query(default=0, ge=0, description="Return events with sequence > this value"),
) -> JobEventsResponse:
    """Poll for new job events since a sequence number.

    Store ``last_sequence`` from each response and pass it as ``?since=<n>``
    on the next poll to receive only new events.
    """
    job_repo = JobRepository(session)
    job = await job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    events = await job_repo.get_events_since(job_id, since_sequence=since)
    last_seq = events[-1].sequence if events else since
    return JobEventsResponse(
        events=[JobEventResponse.model_validate(e) for e in events],
        last_sequence=last_seq,
    )
