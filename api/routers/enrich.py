from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, DbSession
from api.schemas.enrich import (
    PivotLinkResponse,
    PivotsResponse,
    SiteResultResponse,
    UsernameEnumResponse,
)
from scraper.enrich.pivots import build_pivots
from scraper.enrich.username_enum import enumerate_username, is_valid_username
from storage.repositories.account_repo import AccountRepository

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


@router.get("/pivots/{platform}/{handle}", response_model=PivotsResponse)
async def get_pivots(
    platform: str,
    handle: str,
    _key: ApiKeyCheck,
    session: DbSession,
) -> PivotsResponse:
    """OSINT pivot links for an account: reverse-image, identity, breach, dorks.

    Pure link construction over already-collected public fields (profile photo,
    name, bio emails, website). The links open third-party search tools the
    analyst drives manually — no scraping happens here.
    """
    bare = handle.lstrip("@").strip()
    if not is_valid_username(bare):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid handle",
        )

    account = await AccountRepository(session).get_by_username(bare, platform=platform)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {platform}/{bare} not found",
        )

    links = build_pivots(account)
    return PivotsResponse(
        handle=account.username,
        display_name=account.display_name,
        profile_image_url=account.profile_image_url,
        links=[PivotLinkResponse(label=p.label, url=p.url, group=p.group) for p in links],
    )
