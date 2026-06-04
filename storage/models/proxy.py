from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base

_JSON = JSONB().with_variant(JSON(), "sqlite")


class ProxyRecord(Base):
    """A proxy entry from the pool, with liveness and performance tracking."""

    __tablename__ = "proxy_record"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String, nullable=False, default="http")
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    # Country code inferred from GeoIP or proxy provider metadata
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Consecutive failures before marking dead
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Average latency in milliseconds over recent successful requests
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Source of this proxy entry (e.g. "proxyscrape", "user_file", "manual")
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_proxy_record_is_alive", "is_alive"),
        Index("ix_proxy_record_last_used_at", "last_used_at"),
        Index("ix_proxy_record_host_port", "host", "port"),
    )

    @property
    def url(self) -> str:
        """Return the proxy URL in standard form."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def __repr__(self) -> str:
        return f"<ProxyRecord {self.host}:{self.port} alive={self.is_alive}>"
