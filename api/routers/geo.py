from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Query, Request

from api.dependencies import ApiKeyCheck, DbSession
from api.schemas.geo import (
    GeoLocationsResponse,
    GeoPointResponse,
    TimezoneOnlyResponse,
)
from scraper.analysis.geo import (
    GeoResult,
    nominatim_geocode,
    normalize_location,
    tz_offset_to_lon,
)
from storage.models.account import Account
from storage.repositories.account_repo import AccountRepository
from storage.repositories.geocode_repo import GeocodeRepository

router = APIRouter(prefix="/geo", tags=["geo"])


def _confidence(importance: float | None, source: str) -> str:
    """Bucket Nominatim importance into a confidence label.

    Tweet geo chips are an *actual tagged* post location → always high.
    """
    if source == "tweet_geo":
        return "high"
    if importance is None:
        return "medium"
    if importance >= 0.6:
        return "high"
    if importance >= 0.4:
        return "medium"
    return "low"


def _get_geocode_lock(request: Request) -> asyncio.Lock:
    """Process-wide lock serialising Nominatim batches (respects 1 req/sec).

    Created lazily so tests that bypass the app lifespan still work.
    """
    lock: asyncio.Lock | None = getattr(request.app.state, "geocode_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.geocode_lock = lock
    return lock


def _candidates(acc: Account) -> list[tuple[str, str, str]]:
    """Return (display_text, normalized_query, source) candidates for an account.

    Tweet geo chips (real tagged post locations) rank before the profile field.
    """
    raw = acc.raw_data or {}
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for chip in raw.get("geo_locations") or []:
        norm = normalize_location(chip)
        if norm and norm not in seen:
            seen.add(norm)
            out.append((chip, norm, "tweet_geo"))
    norm = normalize_location(acc.location)
    if norm and norm not in seen:
        seen.add(norm)
        out.append((acc.location or norm, norm, "profile"))
    return out


@router.get("/locations", response_model=GeoLocationsResponse)
async def get_locations(
    request: Request,
    _key: ApiKeyCheck,
    session: DbSession,
    max_new: int = Query(default=8, ge=0, le=50, description="Max fresh Nominatim lookups this call"),
    limit: int = Query(default=5000, ge=1, le=10000),
) -> GeoLocationsResponse:
    """Map pins for scraped accounts, geocoded via Nominatim (cached, throttled).

    Resolves cached locations instantly and geocodes up to ``max_new`` fresh
    strings per call (1 req/sec). Poll while ``pending > 0`` — the map fills in
    progressively as the cache warms.
    """
    accounts = await AccountRepository(session).all(limit=limit)

    # Build per-account candidates and the global set of unique queries.
    per_account: list[tuple[Account, list[tuple[str, str, str]]]] = []
    unique_queries: set[str] = set()
    for acc in accounts:
        cands = _candidates(acc)
        if cands:
            per_account.append((acc, cands))
            unique_queries.update(c[1] for c in cands)

    repo = GeocodeRepository(session)
    cache = await repo.get_many(unique_queries)
    misses = [q for q in unique_queries if q not in cache]

    if misses:
        lock = _get_geocode_lock(request)
        async with lock:
            # Another request may have filled some misses while we waited.
            cache.update(await repo.get_many(misses))
            todo = [q for q in misses if q not in cache][:max_new]
            if todo:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    for i, q in enumerate(todo):
                        if i:
                            await asyncio.sleep(1.0)  # Nominatim 1 req/sec policy
                        res: GeoResult | None = await nominatim_geocode(q, client=http)
                        cache[q] = await repo.put(q, res)
                await session.commit()

    pending = sum(1 for q in unique_queries if q not in cache)

    # One pin per account (first resolvable candidate — tweet_geo before profile).
    points: list[GeoPointResponse] = []
    located: set[str] = set()
    for acc, cands in per_account:
        for display, norm, source in cands:
            row = cache.get(norm)
            if row is None or not row.found or row.lat is None or row.lon is None:
                continue
            tz = (acc.raw_data or {}).get("timezone") or {}
            points.append(
                GeoPointResponse(
                    username=acc.username,
                    display_name=acc.display_name,
                    location_text=display,
                    geocoded_name=row.display_name,
                    lat=float(row.lat),
                    lon=float(row.lon),
                    source=source,
                    confidence=_confidence(row.importance, source),
                    followers_count=acc.followers_count or 0,
                    scrape_depth=acc.scrape_depth or 0,
                    timezone_utc_offset=tz.get("utc_offset"),
                )
            )
            located.add(acc.username)
            break

    # Accounts with no pin but a posting-rhythm longitude band.
    tz_only: list[TimezoneOnlyResponse] = []
    for acc in accounts:
        if acc.username in located:
            continue
        tz = (acc.raw_data or {}).get("timezone") or {}
        offset = tz.get("utc_offset")
        if offset is None:
            continue
        lon = tz_offset_to_lon(offset)
        if lon is None:
            continue
        tz_only.append(
            TimezoneOnlyResponse(
                username=acc.username,
                display_name=acc.display_name,
                timezone_utc_offset=offset,
                approx_longitude=lon,
            )
        )

    return GeoLocationsResponse(
        points=points,
        timezone_only=tz_only,
        pending=pending,
        total_accounts=len(accounts),
        located=len(located),
    )
