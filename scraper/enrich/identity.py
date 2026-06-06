"""Resolve a handle to real-identity data via public, official APIs.

When someone reuses their Twitter handle on a less-anonymous service, that
service often exposes a real name and self-asserted links to other accounts —
for free, through its public API:

* **GitHub**  (`api.github.com/users/<u>`) — name, company, location, blog,
  public email, linked twitter handle.
* **GitLab**  (`gitlab.com/api/v4/users?username=<u>`) — name, web URL, bio.
* **Keybase** (`keybase.io/_/api/1.0/user/lookup.json`) — full name plus
  *cryptographically proven* links to Twitter / GitHub / Reddit / HN / websites.

Only public, self-published data. No scraping, no keys. A miss simply means the
handle wasn't reused there. Validate the username before calling (it goes into
outbound URLs).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = [
    "IdentityHit",
    "LinkedAccount",
    "github_identity",
    "gitlab_identity",
    "keybase_identity",
    "resolve_identity",
]

_UA = "xint-osint/0.1 (+https://github.com/gahlautabhinav/xint)"


@dataclass
class LinkedAccount:
    service: str | None
    value: str | None
    url: str | None


@dataclass
class IdentityHit:
    source: str                       # "github" | "gitlab" | "keybase"
    url: str | None = None
    real_name: str | None = None
    location: str | None = None
    company: str | None = None
    bio: str | None = None
    email: str | None = None
    linked_accounts: list[LinkedAccount] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def _norm_url(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw if raw.startswith("http") else f"https://{raw}"


async def github_identity(client: httpx.AsyncClient, username: str) -> IdentityHit | None:
    try:
        resp = await client.get(
            f"https://api.github.com/users/{username}",
            headers={"Accept": "application/vnd.github+json"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        d = resp.json()
    except ValueError:
        return None

    linked: list[LinkedAccount] = []
    if d.get("twitter_username"):
        tw = d["twitter_username"]
        linked.append(LinkedAccount("twitter", tw, f"https://x.com/{tw}"))
    if d.get("blog"):
        linked.append(LinkedAccount("website", d["blog"], _norm_url(d["blog"])))

    return IdentityHit(
        source="github",
        url=d.get("html_url"),
        real_name=d.get("name"),
        location=d.get("location"),
        company=d.get("company"),
        bio=d.get("bio"),
        email=d.get("email"),
        linked_accounts=linked,
        extra={
            k: d.get(k)
            for k in ("followers", "public_repos", "created_at", "hireable")
            if d.get(k) is not None
        },
    )


async def gitlab_identity(client: httpx.AsyncClient, username: str) -> IdentityHit | None:
    try:
        resp = await client.get(
            "https://gitlab.com/api/v4/users", params={"username": username}
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        arr = resp.json()
    except ValueError:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    u = arr[0]

    linked: list[LinkedAccount] = []
    if u.get("twitter"):
        linked.append(LinkedAccount("twitter", u["twitter"], None))
    if u.get("website_url"):
        linked.append(LinkedAccount("website", u["website_url"], _norm_url(u["website_url"])))

    return IdentityHit(
        source="gitlab",
        url=u.get("web_url"),
        real_name=u.get("name"),
        location=u.get("location"),
        company=u.get("organization"),
        bio=u.get("bio"),
        linked_accounts=linked,
        extra={k: u.get(k) for k in ("id", "state") if u.get(k) is not None},
    )


async def keybase_identity(client: httpx.AsyncClient, username: str) -> IdentityHit | None:
    try:
        resp = await client.get(
            "https://keybase.io/_/api/1.0/user/lookup.json",
            params={"usernames": username, "fields": "basics,profile,proofs_summary"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        d = resp.json()
    except ValueError:
        return None

    them = d.get("them") or []
    user = next((t for t in them if t), None)  # entries can be null
    if not user:
        return None

    profile = user.get("profile") or {}
    basics = user.get("basics") or {}
    kb_name = basics.get("username", username)

    linked: list[LinkedAccount] = []
    for proof in (user.get("proofs_summary") or {}).get("all") or []:
        linked.append(
            LinkedAccount(
                service=proof.get("proof_type"),
                value=proof.get("nametag"),
                url=proof.get("service_url") or proof.get("proof_url"),
            )
        )

    return IdentityHit(
        source="keybase",
        url=f"https://keybase.io/{kb_name}",
        real_name=profile.get("full_name"),
        location=profile.get("location"),
        bio=profile.get("bio"),
        linked_accounts=linked,
    )


async def resolve_identity(
    username: str,
    *,
    timeout: float = 8.0,
) -> list[IdentityHit]:
    """Query every public identity source for *username*. Pre-validate the input."""
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _UA}) as client:
        hits = await asyncio.gather(
            github_identity(client, username),
            gitlab_identity(client, username),
            keybase_identity(client, username),
        )
    return [h for h in hits if h is not None]
