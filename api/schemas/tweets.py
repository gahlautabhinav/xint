from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TweetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tweet_id: str | None
    text: str
    timestamp: datetime | None
    reply_to: str | None
    quote_url: str | None
    retweeted_from: str | None
    geo_location: str | None
    mentions: list[str] = []
    hashtags: list[str] = []
    scraped_at: datetime
    tweet_url: str | None = None


class TweetListResponse(BaseModel):
    items: list[TweetResponse]
    total: int
