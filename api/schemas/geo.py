from __future__ import annotations

from pydantic import BaseModel


class GeoPointResponse(BaseModel):
    """A single map pin: an account resolved to a coordinate."""

    username: str
    display_name: str | None = None
    location_text: str          # the raw string we geocoded (for display)
    geocoded_name: str | None = None  # Nominatim's resolved place name
    lat: float
    lon: float
    source: str                 # "profile" | "tweet_geo"
    confidence: str             # "high" | "medium" | "low"
    followers_count: int = 0
    scrape_depth: int = 0
    timezone_utc_offset: int | None = None


class TimezoneOnlyResponse(BaseModel):
    """An account with no geocodable string but an inferred posting band."""

    username: str
    display_name: str | None = None
    timezone_utc_offset: int
    approx_longitude: float


class GeoLocationsResponse(BaseModel):
    points: list[GeoPointResponse]
    timezone_only: list[TimezoneOnlyResponse]
    pending: int                # unique strings not yet geocoded (poll again)
    total_accounts: int         # every account row (incl. uncrawled edge stubs)
    scraped_accounts: int       # accounts whose profile was actually fetched
    located: int
