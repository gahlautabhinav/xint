from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base


class SourceField(str, enum.Enum):
    """Where on the source profile the cross-platform link was found."""

    BIO = "BIO"
    WEBSITE = "WEBSITE"
    PINNED_TWEET = "PINNED_TWEET"
    TWEET_BODY = "TWEET_BODY"


class CrossPlatformLink(Base):
    """A detected link from a Twitter account to a profile on another platform."""

    __tablename__ = "cross_platform_link"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_platform: Mapped[str] = mapped_column(String, nullable=False)
    target_handle: Mapped[str] = mapped_column(String, nullable=False)
    target_url: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_field: Mapped[SourceField] = mapped_column(
        Enum(SourceField, name="source_field_enum"),
        nullable=False,
    )
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_cross_platform_link_account_id", "account_id"),
        Index("ix_cross_platform_link_target_platform", "target_platform"),
    )

    def __repr__(self) -> str:
        return (
            f"<CrossPlatformLink account={self.account_id} "
            f"-> {self.target_platform}:{self.target_handle!r}>"
        )
