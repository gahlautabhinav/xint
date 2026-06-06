from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, DbSession
from api.schemas.enrich import (
    BiasAccountResponse,
    BiasStatusResponse,
    BiasVerdictResponse,
    IdentityHitResponse,
    IdentityResponse,
    LinkedAccountResponse,
    PivotLinkResponse,
    PivotsResponse,
    SiteResultResponse,
    UsernameEnumResponse,
)
from config.settings import get_settings
from scraper.enrich.identity import resolve_identity
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


@router.get("/identity", response_model=IdentityResponse)
async def get_identity(
    _key: ApiKeyCheck,
    username: str = Query(..., min_length=1, max_length=40),
) -> IdentityResponse:
    """Resolve a handle to real-identity data via public APIs (GitHub/GitLab/Keybase).

    When the handle was reused on one of these services, returns the real name,
    location, company and self-asserted linked accounts it publishes. A miss
    means the handle wasn't found there. Public self-published data only.
    """
    handle = username.lstrip("@").strip()
    if not is_valid_username(handle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username: only letters, digits, '_', '.', '-' are allowed",
        )

    hits = await resolve_identity(handle)
    return IdentityResponse(
        username=handle,
        hits=[
            IdentityHitResponse(
                source=h.source,
                url=h.url,
                real_name=h.real_name,
                location=h.location,
                company=h.company,
                bio=h.bio,
                email=h.email,
                linked_accounts=[
                    LinkedAccountResponse(service=la.service, value=la.value, url=la.url)
                    for la in h.linked_accounts
                ],
                extra=h.extra,
            )
            for h in hits
        ],
    )


@router.get("/bias/status", response_model=BiasStatusResponse)
async def bias_status(_key: ApiKeyCheck) -> BiasStatusResponse:
    """Check whether the xint-bias-agent is reachable."""
    url = get_settings().BIAS_AGENT_URL
    if not url:
        return BiasStatusResponse(connected=False, url=None)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/health")
        return BiasStatusResponse(connected=resp.status_code == 200, url=url)
    except Exception:
        return BiasStatusResponse(connected=False, url=url)


@router.get("/bias", response_model=list[BiasAccountResponse])
async def list_bias_flags(_key: ApiKeyCheck) -> list[BiasAccountResponse]:
    """Return all accounts the bias agent has analyzed, newest first."""
    url = get_settings().BIAS_AGENT_URL
    if not url:
        raise HTTPException(status_code=503, detail="Bias agent not configured — set BIAS_AGENT_URL in .env")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/flags")
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bias agent unreachable: {exc}") from exc
    return [
        BiasAccountResponse(
            username=r["username"],
            analyzed=True,
            verdict=BiasVerdictResponse.model_validate(r),
            updated_at=r.get("updated_at"),
        )
        for r in resp.json()
    ]


@router.get("/bias/{username}", response_model=BiasAccountResponse)
async def get_bias_flags(
    username: str,
    _key: ApiKeyCheck,
) -> BiasAccountResponse:
    """Return bias flags for a specific handle from the bias agent."""
    bare = username.lstrip("@").strip()
    if not is_valid_username(bare):
        raise HTTPException(status_code=400, detail="Invalid username")
    url = get_settings().BIAS_AGENT_URL
    if not url:
        raise HTTPException(status_code=503, detail="Bias agent not configured — set BIAS_AGENT_URL in .env")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/flags/{bare}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bias agent unreachable: {exc}") from exc
    if resp.status_code == 404:
        return BiasAccountResponse(username=bare, analyzed=False)
    resp.raise_for_status()
    data = resp.json()
    return BiasAccountResponse(
        username=bare,
        analyzed=True,
        verdict=BiasVerdictResponse.model_validate(data),
        updated_at=data.get("updated_at"),
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
