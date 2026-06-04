from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.job import CrawlJob, JobEvent, JobQueueItem


class JobRepository:
    """Data-access layer for :class:`~storage.models.job.CrawlJob` and
    :class:`~storage.models.job.JobEvent` records.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # CrawlJob operations
    # ------------------------------------------------------------------

    async def create_job(self, **kwargs: Any) -> CrawlJob:
        """Persist a new :class:`CrawlJob` and return it."""
        job = CrawlJob(**kwargs)
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_job(self, job_id: uuid.UUID) -> CrawlJob | None:
        """Return a :class:`CrawlJob` by primary key, or ``None``."""
        stmt = select(CrawlJob).where(CrawlJob.id == job_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_job(
        self,
        job_id: uuid.UUID,
        **kwargs: Any,
    ) -> CrawlJob | None:
        """Update fields on an existing job.

        Returns the updated :class:`CrawlJob`, or ``None`` if not found.
        Always stamps ``updated_at`` with the current UTC time.
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        skip = {"id"}
        for key, value in kwargs.items():
            if key not in skip:
                setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return job

    async def delete_job(self, job_id: uuid.UUID) -> bool:
        """Delete a job and its child rows (events, queue items).

        SQLite does not honour the declared ``ondelete=CASCADE`` unless
        ``PRAGMA foreign_keys=ON`` (it is OFF here), so children are deleted
        explicitly first to avoid orphan rows. Returns ``True`` if a job row
        was removed.
        """
        await self._session.execute(delete(JobEvent).where(JobEvent.job_id == job_id))
        await self._session.execute(
            delete(JobQueueItem).where(JobQueueItem.job_id == job_id)
        )
        result = await self._session.execute(delete(CrawlJob).where(CrawlJob.id == job_id))
        await self._session.flush()
        return bool(cast("CursorResult[Any]", result).rowcount)

    async def list_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrawlJob]:
        """Return jobs ordered by creation time descending."""
        stmt = (
            select(CrawlJob)
            .order_by(CrawlJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # JobEvent operations
    # ------------------------------------------------------------------

    async def emit_event(
        self,
        job_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> JobEvent:
        """Append a new event to the job's event log.

        The ``sequence`` number is auto-incremented by finding the current
        maximum sequence for this job and adding 1.  This is safe for our
        single-writer async pattern (no concurrent writers per job).
        """
        stmt = select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)
        result = await self._session.execute(stmt)
        current_max: int | None = result.scalar_one_or_none()
        next_sequence = (current_max or 0) + 1

        event = JobEvent(
            job_id=job_id,
            sequence=next_sequence,
            event_type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def get_events_since(
        self,
        job_id: uuid.UUID,
        since_sequence: int,
    ) -> list[JobEvent]:
        """Return all events for *job_id* with ``sequence > since_sequence``.

        Ordered by sequence ascending, suitable for replay / streaming.
        """
        stmt = (
            select(JobEvent)
            .where(
                JobEvent.job_id == job_id,
                JobEvent.sequence > since_sequence,
            )
            .order_by(JobEvent.sequence)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
