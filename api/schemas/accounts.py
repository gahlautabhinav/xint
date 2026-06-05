from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    platform: str
    display_name: str | None
    bio: str | None
    website: str | None
    location: str | None = None
    profile_image_url: str | None = None
    followers_count: int
    following_count: int
    tweet_count: int = 0
    is_verified: bool
    scraped_at: datetime | None
    scrape_depth: int
    # Extracted from raw_data JSON column
    join_date: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    timezone_utc_offset: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _extract_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        raw: dict[str, Any] = getattr(data, "raw_data", None) or {}
        tz: dict[str, Any] = raw.get("timezone") or {}
        return {
            "id": data.id,
            "username": data.username,
            "platform": data.platform,
            "display_name": data.display_name,
            "bio": data.bio,
            "website": data.website,
            "location": data.location,
            "profile_image_url": getattr(data, "profile_image_url", None),
            "followers_count": data.followers_count,
            "following_count": data.following_count,
            "tweet_count": getattr(data, "tweet_count", 0) or 0,
            "is_verified": data.is_verified,
            "scraped_at": data.scraped_at,
            "scrape_depth": data.scrape_depth,
            "join_date": raw.get("join_date"),
            "emails": raw.get("emails") or [],
            "phones": raw.get("phones") or [],
            "timezone_utc_offset": tz.get("utc_offset"),
        }


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
