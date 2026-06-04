from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

_JSON = JSONB().with_variant(JSON(), "sqlite")


class JobStatus(str, enum.Enum):
    """Top-level status of a crawl job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QueueItemStatus(str, enum.Enum):
    """Status of an individual item within a job's work queue."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CrawlJob(Base):
    """A top-level crawl job initiated by the user."""

    __tablename__ = "crawl_job"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    seed_username: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False, default="twitter")
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    accounts_scraped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accounts_queued: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_crawl_job_status", "status"),
        Index("ix_crawl_job_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CrawlJob id={self.id} seed={self.seed_username!r} status={self.status.value}>"


class JobQueueItem(Base):
    """An individual account enqueued for scraping within a CrawlJob."""

    __tablename__ = "job_queue_item"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False, default="twitter")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[QueueItemStatus] = mapped_column(
        Enum(QueueItemStatus, name="queue_item_status_enum"),
        nullable=False,
        default=QueueItemStatus.PENDING,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_job_queue_item_job_id", "job_id"),
        Index("ix_job_queue_item_status", "status"),
        Index("ix_job_queue_item_priority", "priority"),
    )

    def __repr__(self) -> str:
        return (
            f"<JobQueueItem job={self.job_id} username={self.username!r} "
            f"depth={self.depth} status={self.status.value}>"
        )


class JobEvent(Base):
    """Structured event log for a CrawlJob (Phase 5 streaming flag)."""

    __tablename__ = "job_event"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_job_event_job_id", "job_id"),
        Index("ix_job_event_job_id_sequence", "job_id", "sequence"),
    )

    def __repr__(self) -> str:
        return (
            f"<JobEvent job={self.job_id} seq={self.sequence} type={self.event_type!r}>"
        )
