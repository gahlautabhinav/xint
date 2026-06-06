from __future__ import annotations

from pydantic import BaseModel


class SiteResultResponse(BaseModel):
    name: str
    category: str
    url: str
    status: str  # "found" | "not_found" | "unknown"


class UsernameEnumResponse(BaseModel):
    username: str
    checked: int
    found: int
    results: list[SiteResultResponse]
