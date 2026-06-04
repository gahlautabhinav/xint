from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
