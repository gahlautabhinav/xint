from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

# Cross-database JSON type: JSONB on Postgres, JSON on SQLite
_JSON = JSONB().with_variant(JSON(), "sqlite")


class Account(Base):
    """Scraped Twitter/X account (or cross-platform account)."""

    __tablename__ = "account"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False, default="twitter")
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    followers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tweet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Account creation date on the platform (not our record creation time)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When we last scraped this account
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scrape_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("platform", "username", name="uq_account_platform_username"),
        Index("ix_account_scraped_at", "scraped_at"),
        Index("ix_account_scrape_depth", "scrape_depth"),
    )

    def __repr__(self) -> str:
        return f"<Account platform={self.platform!r} username={self.username!r}>"
