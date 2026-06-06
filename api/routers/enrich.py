from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck
from api.schemas.enrich import SiteResultResponse, UsernameEnumResponse
from scraper.enrich.username_enum import enumerate_username, is_valid_username

router = APIRouter(prefix="/enrich", tags=["enrich"])


@router.get("/username", response_model=UsernameEnumResponse)
async def enum_username(
    _key: ApiKeyCheck,
    username: str = Query(..., min_length=1, max_length=40),
) -> UsernameEnumResponse:
    """Check whether *username* exists across many public sites (Sherlock-style).

    Probes ~30 sites concurrently and reports found / not_found / unknown for
    each. Operates on public profile URLs only. The username is strictly
    validated before being interpolated into outbound requests.
    """
    handle = username.lstrip("@").strip()
    if not is_valid_username(handle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username: only letters, digits, '_', '.', '-' are allowed",
        )

    results = await enumerate_username(handle)
    return UsernameEnumResponse(
        username=handle,
        checked=len(results),
        found=sum(1 for r in results if r.status == "found"),
        results=[
            SiteResultResponse(name=r.name, category=r.category, url=r.url, status=r.status)
            for r in results
        ],
    )
