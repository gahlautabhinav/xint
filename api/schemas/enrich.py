from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


# ── Bias agent ────────────────────────────────────────────────────────────────

class BiasVerdictResponse(BaseModel):
    is_antisemitic: bool = False
    is_anti_jew: bool = False
    is_anti_israel: bool = False
    is_anti_zionist: bool = False
    is_pro_islamist_extremist: bool = False
    is_pro_hamas_hezbollah: bool = False
    is_pro_palestine: bool = False
    is_white_supremacist: bool = False
    is_neo_nazi: bool = False
    evidence: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class BiasAccountResponse(BaseModel):
    username: str
    analyzed: bool
    verdict: BiasVerdictResponse | None = None
    updated_at: str | None = None


class BiasStatusResponse(BaseModel):
    connected: bool
    url: str | None = None
