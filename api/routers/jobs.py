from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, status

from api.dependencies import ApiKeyCheck, DbSession, GraphBackend
from api.schemas.jobs import (
    JobCreate,
    JobEventResponse,
    JobEventsResponse,
    JobListResponse,
    JobResponse,
)
from scraper.jobs.crawler import AccountCrawler, CrawlerConfig
from storage.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def create_job(
    body: JobCreate,
    request: Request,
    _key: ApiKeyCheck,
    session: DbSession,
    graph: GraphBackend,
) -> JobResponse:
    """Start a crawl job. Returns 202 immediately; crawl runs in the background."""
    session_factory = request.app.state.session_factory

    config = CrawlerConfig(
        seed_username=body.seed_username,
        max_depth=body.max_depth,
        max_accounts=body.max_accounts,
        rate_profile_name=body.rate_profile,  # type: ignore[arg-type]
        proxy_urls=body.proxy_urls,
    )

    crawler = AccountCrawler(
        config=config,
        session_factory=session_factory,
        graph=graph,
    )

    asyncio.create_task(crawler.run(), name=f"crawl-{body.seed_username}")

    # Yield once so the crawler can flush the initial job INSERT before we query.
    await asyncio.sleep(0)

    job_repo = JobRepository(session)
    jobs = await job_repo.list_jobs(limit=1, offset=0)
    if jobs:
        return JobResponse.model_validate(jobs[0])

    # Rare race: return a synthetic preview if the INSERT hasn't landed yet.
    return JobResponse(
        id=uuid.uuid4(),
        seed_username=body.seed_username,
        platform="twitter",
        max_depth=body.max_depth,
        max_accounts=body.max_accounts,
        status="RUNNING",
        accounts_scraped=0,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
    )


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
