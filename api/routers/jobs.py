from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from api.dependencies import ApiKeyCheck, DbSession, GraphBackend
from api.schemas.jobs import (
    DiscoverRequest,
    DiscoverResponse,
    JobCreate,
    JobEventResponse,
    JobEventsResponse,
    JobListResponse,
    JobResponse,
)
from graph.schema.nodes import make_node_id, parse_node_id
from scraper.jobs.crawler import CrawlerConfig
from scraper.jobs.runner import run_crawl_in_thread
from storage.models.account import Account
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
        max_following=body.max_following,
        max_followers=body.max_followers,
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


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED, response_model=DiscoverResponse)
async def discover_all(
    body: DiscoverRequest,
    _key: ApiKeyCheck,
    session: DbSession,
    graph: GraphBackend,
) -> DiscoverResponse:
    """Crawl uncrawled (stub) accounts in a seed's graph so they can be located.

    Walks the seed's subgraph, finds accounts that are mere edge endpoints
    (``raw_data`` is NULL — never scraped), and enriches up to ``max_accounts``
    of them in one batched job (profile + tweets only, no list expansion). Run
    again for the next batch.
    """
    node_id = make_node_id(body.platform, body.seed)
    data = await graph.get_subgraph(node_id, depth=body.depth, limit=10000)
    if not data["nodes"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{body.platform}/{body.seed} not in graph — crawl it first",
        )

    # Collect twitter handles in the seed's network (excluding the seed itself).
    seed_handle = body.seed.lstrip("@").lower()
    handles: list[str] = []
    seen: set[str] = set()
    for n in data["nodes"]:
        try:
            platform, handle = parse_node_id(n["node_id"])
        except ValueError:
            continue
        if platform != body.platform:
            continue
        h = handle.lstrip("@").lower()
        if h == seed_handle or h in seen:
            continue
        seen.add(h)
        handles.append(h)

    if not handles:
        return DiscoverResponse(job_id=None, queued=0, remaining=0)

    # Which of those have never been scraped (raw_data IS NULL)? Filter in Python
    # against the set of all uncrawled usernames — avoids a huge SQL ``IN`` list
    # (SQLite caps bound variables) and preserves subgraph order for batching.
    stmt = select(Account.username).where(
        Account.platform == body.platform,
        Account.raw_data.is_(None),
    )
    uncrawled_set = {u.lower() for u in (await session.execute(stmt)).scalars().all()}
    uncrawled = [h for h in handles if h in uncrawled_set]
    if not uncrawled:
        return DiscoverResponse(job_id=None, queued=0, remaining=0)

    batch = uncrawled[: body.max_accounts]
    remaining = len(uncrawled) - len(batch)

    config = CrawlerConfig(
        seed_username=body.seed,
        max_depth=body.depth,
        max_accounts=len(batch),
        rate_profile_name=body.rate_profile,  # type: ignore[arg-type]
        proxy_urls=body.proxy_urls,
        scrape_following=False,
        scrape_followers=False,
        target_usernames=batch,
        expand=False,
    )

    job_repo = JobRepository(session)
    job = await job_repo.create_job(
        seed_username=body.seed,
        max_depth=body.depth,
        max_accounts=len(batch),
        status=JobStatus.PENDING,
    )
    await session.refresh(job)
    job_id = job.id
    await session.commit()

    threading.Thread(
        target=run_crawl_in_thread,
        args=(config, graph, job_id),
        name=f"discover-{body.seed}",
        daemon=True,
    ).start()

    return DiscoverResponse(job_id=job_id, queued=len(batch), remaining=remaining)


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


@router.post(
    "/{job_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobResponse,
)
async def cancel_job(
    job_id: uuid.UUID,
    _key: ApiKeyCheck,
    session: DbSession,
) -> JobResponse:
    """Cooperatively cancel a running/pending crawl.

    Flips the job's status to CANCELLED; the crawl worker notices at its next
    BFS iteration boundary and stops cleanly. No-op-rejects (409) a job that
    has already reached a terminal state.
    """
    job_repo = JobRepository(session)
    job = await job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is {job.status.value}; only running jobs can be cancelled",
        )
    updated = await job_repo.update_job(job_id, status=JobStatus.CANCELLED)
    assert updated is not None  # get_job above confirmed it exists
    return JobResponse.model_validate(updated)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    _key: ApiKeyCheck,
    session: DbSession,
) -> None:
    """Delete a job and its events. Running/pending jobs must be stopped first."""
    job_repo = JobRepository(session)
    job = await job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is running; cancel (stop) it before deleting",
        )
    await job_repo.delete_job(job_id)


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
