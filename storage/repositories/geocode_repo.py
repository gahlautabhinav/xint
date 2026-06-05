from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.analysis.geo import GeoResult
from storage.models.geocode import GeocodeCache


class GeocodeRepository:
    """Read/write access to the :class:`GeocodeCache` table.

    Negative results (``found=False``) are stored deliberately so junk strings
    are never re-sent to Nominatim.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, queries: Iterable[str]) -> dict[str, GeocodeCache]:
        """Return cached rows for the given queries, keyed by query string."""
        keys = list(set(queries))
        if not keys:
            return {}
        stmt = select(GeocodeCache).where(GeocodeCache.query.in_(keys))
        result = await self._session.execute(stmt)
        return {row.query: row for row in result.scalars().all()}

    async def put(self, query: str, result: GeoResult | None) -> GeocodeCache:
        """Upsert a geocode result (or a negative cache entry when ``None``)."""
        existing = await self._session.get(GeocodeCache, query)
        if existing is None:
            existing = GeocodeCache(query=query)
            self._session.add(existing)
        if result is None:
            existing.found = False
            existing.lat = None
            existing.lon = None
            existing.display_name = None
            existing.importance = None
        else:
            existing.found = True
            existing.lat = result.lat
            existing.lon = result.lon
            existing.display_name = result.display_name
            existing.importance = result.importance
        await self._session.flush()
        return existing
