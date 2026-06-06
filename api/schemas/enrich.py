from __future__ import annotations

from typing import Any

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


class PivotLinkResponse(BaseModel):
    label: str
    url: str
    group: str  # "reverse_image" | "identity" | "dork" | "breach"


class PivotsResponse(BaseModel):
    handle: str
    display_name: str | None = None
    profile_image_url: str | None = None
    links: list[PivotLinkResponse]


class LinkedAccountResponse(BaseModel):
    service: str | None = None
    value: str | None = None
    url: str | None = None


class IdentityHitResponse(BaseModel):
    source: str
    url: str | None = None
    real_name: str | None = None
    location: str | None = None
    company: str | None = None
    bio: str | None = None
    email: str | None = None
    linked_accounts: list[LinkedAccountResponse] = []
    extra: dict[str, Any] = {}


class IdentityResponse(BaseModel):
    username: str
    hits: list[IdentityHitResponse]
