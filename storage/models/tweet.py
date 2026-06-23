from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

_JSON = JSONB().with_variant(JSON(), "sqlite")


class Tweet(Base):
    __tablename__ = "tweet"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    tweet_id: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    quote_url: Mapped[str | None] = mapped_column(String, nullable=True)
    retweeted_from: Mapped[str | None] = mapped_column(String, nullable=True)
    geo_location: Mapped[str | None] = mapped_column(String, nullable=True)
    mentions: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    hashtags: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    media_urls: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("account_id", "tweet_id", name="uq_tweet_account_tweet_id"),
        Index("ix_tweet_account_id", "account_id"),
        Index("ix_tweet_timestamp", "timestamp"),
        Index("ix_tweet_tweet_id", "tweet_id"),
    )

    def __repr__(self) -> str:
        return f"<Tweet account_id={self.account_id} tweet_id={self.tweet_id!r}>"
