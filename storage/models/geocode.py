from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from storage.base import Base


class GeocodeCache(Base):
    """Persistent cache of Nominatim geocoding results, keyed by query string.

    The OSM Nominatim usage policy caps requests at ~1/sec, so every resolved
    location string is cached here — including *negative* results (``found=False``)
    so junk strings ("she/her", "planet earth") are never re-queried. ``query``
    is the normalised, lower-cased location string (see
    :func:`scraper.analysis.geo.normalize_location`).
    """

    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(String, primary_key=True)
    found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    importance: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<GeocodeCache query={self.query!r} found={self.found}>"
