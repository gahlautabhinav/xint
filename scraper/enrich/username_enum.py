"""Check whether a username exists across many sites (Sherlock-style).

Probes each site in :data:`scraper.enrich.sites.SITES` concurrently and reports
``found`` / ``not_found`` / ``unknown``. Operates only on public profile URLs.

Security: the username is interpolated into outbound URLs, so the caller MUST
validate it against :func:`is_valid_username` first (strict charset) — this
prevents path-traversal / URL-injection into third-party requests.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

from scraper.enrich.sites import SITES, Site

__all__ = [
    "SiteResult",
    "USERNAME_RE",
    "detect",
    "enumerate_username",
    "is_valid_username",
]

# A browser-like UA: some sites 403 obvious bots. Not evasion — just politeness.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Conservative: alphanumerics plus the few separators real handles use. Length
# capped so a pathological value can't build a huge URL. Rejects '/', '?', etc.
USERNAME_RE = re.compile(r"[A-Za-z0-9_.\-]{1,40}")


def is_valid_username(username: str) -> bool:
    """True if *username* is safe to interpolate into outbound URLs."""
    return bool(USERNAME_RE.fullmatch(username))


@dataclass
class SiteResult:
    name: str
    category: str
    url: str
    status: str  # "found" | "not_found" | "unknown"


def detect(site: Site, status_code: int, text: str) -> str:
    """Classify one response into found / not_found / unknown for *site*."""
    if site.check == "status":
        if status_code == 200:
            return "found"
        if status_code == 404:
            return "not_found"
        return "unknown"

    # Marker-based checks need a 200 body; non-200 is treated as not_found (404)
    # or unknown (blocked/errored).
    if status_code != 200:
        return "not_found" if status_code == 404 else "unknown"
    if site.marker is None:
        return "unknown"
    present = site.marker in text
    if site.check == "absent":
        return "not_found" if present else "found"
    if site.check == "present":
        return "found" if present else "not_found"
    return "unknown"


async def _check_site(
    client: httpx.AsyncClient,
    site: Site,
    username: str,
    sem: asyncio.Semaphore,
) -> SiteResult:
    url = site.url.format(username=username)
    async with sem:
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            return SiteResult(site.name, site.category, url, "unknown")
    text = resp.text if site.check != "status" else ""
    return SiteResult(site.name, site.category, url, detect(site, resp.status_code, text))


async def enumerate_username(
    username: str,
    *,
    sites: list[Site] | None = None,
    concurrency: int = 12,
    timeout: float = 8.0,
) -> list[SiteResult]:
    """Probe every site for *username*. Caller must pre-validate the username."""
    targets = sites if sites is not None else SITES
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": _UA}
    ) as client:
        results = await asyncio.gather(
            *(_check_site(client, s, username, sem) for s in targets)
        )
    return list(results)
