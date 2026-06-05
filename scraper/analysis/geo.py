"""Geocode account location strings via OpenStreetMap Nominatim.

Profile location fields are noisy ("SF 🌉", "she/her", "Planet Earth 🌍",
"127.0.0.1"). We normalise first — strip emoji / symbols, collapse whitespace,
reject obvious non-places — then resolve survivors through Nominatim. Results
(positive *and* negative) are cached upstream so the 1 req/sec policy is only
ever paid once per unique string.

Timezone offset gives a coarse longitude fallback (offset × 15°) for accounts
whose location field won't geocode but whose posting rhythm betrays a band.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

__all__ = [
    "GeoResult",
    "NOMINATIM_URL",
    "USER_AGENT",
    "nominatim_geocode",
    "normalize_location",
    "tz_offset_to_lon",
]

# OSM Nominatim public endpoint. Policy: max 1 req/sec, identifying User-Agent
# required. Contact is the public repo URL (no email).
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "xint-osint/0.1 (+https://github.com/gahlautabhinav/xint)"

# Strings that occupy the location field but name no place. Lower-cased.
_JUNK_TOKENS = frozenset(
    {
        "she", "her", "hers", "he", "him", "his", "they", "them", "theirs",
        "she/her", "he/him", "they/them",
        "everywhere", "anywhere", "nowhere", "somewhere", "here", "there",
        "earth", "planet earth", "the earth", "world", "the world", "worldwide",
        "global", "globe", "international", "online", "the internet", "internet",
        "web", "cyberspace", "metaverse", "matrix", "home", "n/a", "na", "none",
        "tba", "tbd", "moon", "mars", "space", "your mom", "your heart", "dms",
        "your head", "behind you", "right behind you", "404", "localhost",
    }
)

# Keep letters (any script), digits, and a few separators; drop emoji / symbols.
_KEEP_RE = re.compile(r"[^\w\s,.'/&\-]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


@dataclass
class GeoResult:
    """A resolved coordinate from Nominatim."""

    lat: float
    lon: float
    display_name: str
    importance: float | None = None


def normalize_location(text: str | None) -> str | None:
    """Clean a raw location string into a geocodable query, or ``None``.

    Returns a lower-cased, symbol-stripped string suitable as a Nominatim query
    and a stable cache key. ``None`` means "not worth geocoding" (empty, junk,
    or no real letters).
    """
    if not text:
        return None
    s = _KEEP_RE.sub(" ", text)
    s = _WS_RE.sub(" ", s).strip()
    s = s.strip(" ,.-/&'")
    if len(s) < 2:
        return None
    # Need at least two alphabetic characters — kills "12345", "•", etc.
    if sum(c.isalpha() for c in s) < 2:
        return None
    low = s.lower()
    if low in _JUNK_TOKENS:
        return None
    return low


def tz_offset_to_lon(offset: int | None) -> float | None:
    """Map a UTC offset to an approximate central longitude (offset × 15°)."""
    if offset is None:
        return None
    return max(-180.0, min(180.0, offset * 15.0))


async def nominatim_geocode(
    query: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 10.0,
) -> GeoResult | None:
    """Resolve a single query via Nominatim. Returns ``None`` on no-match / error.

    Rate limiting (≥1s between calls) is the *caller's* responsibility — this
    function makes exactly one request. Pass a shared ``client`` to reuse the
    connection across a batch.
    """
    own = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await c.get(
            NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None
        top = data[0]
        imp = top.get("importance")
        return GeoResult(
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            display_name=str(top.get("display_name") or query),
            importance=float(imp) if imp is not None else None,
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    finally:
        if own:
            await c.aclose()
