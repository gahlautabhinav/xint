from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    seed_username: str = Field(min_length=1, max_length=100)
    max_depth: int = Field(default=2, ge=1, le=5)
    max_accounts: int = Field(default=500, ge=1, le=10000)
    max_following: int = Field(default=50, ge=1, le=5000)
    max_followers: int = Field(default=50, ge=1, le=5000)
    rate_profile: str = Field(default="moderate")
    proxy_urls: list[str] = Field(default_factory=list)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seed_username: str
    platform: str
    max_depth: int
    max_accounts: int
    status: str
    accounts_scraped: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class DiscoverRequest(BaseModel):
    """Start an enrichment crawl of uncrawled accounts in a seed's graph."""

    seed: str = Field(min_length=1, max_length=100)
    depth: int = Field(default=2, ge=1, le=5)
    max_accounts: int = Field(default=200, ge=1, le=2000)
    # The crawler scrapes Twitter/X only — enforce it so discovered handles are
    # never mislabelled or sent to the wrong site.
    platform: Literal["twitter"] = "twitter"
    rate_profile: str = Field(default="moderate")
    proxy_urls: list[str] = Field(default_factory=list)


class DiscoverResponse(BaseModel):
    job_id: uuid.UUID | None  # None when there was nothing to crawl
    queued: int               # how many uncrawled accounts this run will visit
    remaining: int            # uncrawled accounts still left after this batch


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    sequence: int
    event_type: str
    payload: dict[str, Any] | None
    created_at: datetime


class JobEventsResponse(BaseModel):
    events: list[JobEventResponse]
    last_sequence: int


class AnalyzeNowRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    rate_profile: str = Field(default="moderate")
    proxy_urls: list[str] = Field(default_factory=list)


class AnalyzeNowResponse(BaseModel):
    job_id: uuid.UUID
    username: str
    status: str


class RescrapeRequest(BaseModel):
    """Re-scrape already-scraped accounts to refresh their data.

    Leave *usernames* empty to re-scrape every account that has been
    scraped at least once (``raw_data IS NOT NULL``). Pass a list to
    target specific handles.
    """

    usernames: list[str] = Field(default_factory=list)
    rate_profile: str = Field(default="moderate")
    proxy_urls: list[str] = Field(default_factory=list)
    platform: Literal["twitter"] = "twitter"


class RescrapeResponse(BaseModel):
    job_id: uuid.UUID | None
    queued: int
    status: str
