from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

_JSON = JSONB().with_variant(JSON(), "sqlite")


class RawScrapeResult(Base):
    """Raw HTML/JSON payload captured during a scrape pass, before parsing."""

    __tablename__ = "raw_scrape_result"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    # Optional FK — raw results may exist before account record is created
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Optional FK — tied to the job that triggered the scrape
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_job.id", ondelete="SET NULL"),
        nullable=True,
    )
    username: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False, default="twitter")
    scrape_type: Mapped[str] = mapped_column(String, nullable=False)
    # The raw payload (HTML snippet, JSON blob, etc.)
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Whether this result was successfully parsed into structured data
    parsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parse_error: Mapped[str | None] = mapped_column(String, nullable=True)
    proxy_used: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_raw_scrape_result_account_id", "account_id"),
        Index("ix_raw_scrape_result_job_id", "job_id"),
        Index("ix_raw_scrape_result_username", "username"),
        Index("ix_raw_scrape_result_scraped_at", "scraped_at"),
        Index("ix_raw_scrape_result_parsed", "parsed"),
    )

    def __repr__(self) -> str:
        return (
            f"<RawScrapeResult username={self.username!r} "
            f"type={self.scrape_type!r} parsed={self.parsed}>"
        )
