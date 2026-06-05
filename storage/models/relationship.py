from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

_JSON = JSONB().with_variant(JSON(), "sqlite")


class RelType(str, enum.Enum):
    """Type of relationship between two accounts."""

    FOLLOWS = "FOLLOWS"
    MENTIONS = "MENTIONS"
    REPLIES_TO = "REPLIES_TO"
    QUOTE_TWEETS = "QUOTE_TWEETS"
    RETWEETS = "RETWEETS"
    CROSS_PLATFORM_LINK = "CROSS_PLATFORM_LINK"


class Relationship(Base):
    """Directed relationship between two accounts."""

    __tablename__ = "relationship"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    source_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    rel_type: Mapped[RelType] = mapped_column(
        Enum(RelType, name="rel_type_enum"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Named metadata_ to avoid shadowing SQLAlchemy's .metadata attribute
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "_metadata", _JSON, nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "source_account_id",
            "target_account_id",
            "rel_type",
            name="uq_relationship_source_target_type",
        ),
        Index("ix_relationship_source_account_id", "source_account_id"),
        Index("ix_relationship_target_account_id", "target_account_id"),
        Index("ix_relationship_rel_type", "rel_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<Relationship {self.source_account_id} --{self.rel_type.value}--> "
            f"{self.target_account_id}>"
        )
