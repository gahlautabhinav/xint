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


class PivotLinkResponse(BaseModel):
    label: str
    url: str
    group: str  # "reverse_image" | "identity" | "dork" | "breach"


class PivotsResponse(BaseModel):
    handle: str
    display_name: str | None = None
    profile_image_url: str | None = None
    links: list[PivotLinkResponse]
