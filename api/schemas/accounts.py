from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    platform: str
    display_name: str | None
    bio: str | None
    website: str | None
    followers_count: int
    following_count: int
    is_verified: bool
    scraped_at: datetime | None
    scrape_depth: int


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
