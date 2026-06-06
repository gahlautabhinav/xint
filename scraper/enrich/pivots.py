"""Build OSINT "pivot" links for an account — ways to investigate it further.

Everything here is pure link construction over already-collected public data
(profile image, display name, bio emails, website). No network calls: the links
open third-party search engines the analyst drives manually, which keeps us
within those sites' ToS and adds no scraping load.

Groups:
* ``reverse_image`` — reverse-search the profile photo (Google Lens, Yandex,
  TinEye, Bing) to find the same face/picture elsewhere.
* ``identity``      — Gravatar (from email), Wayback snapshots, website.
* ``dork``          — pre-built Google searches for the handle / name / emails.
* ``breach``        — exposure lookups for found emails (Dehashed, IntelX).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

__all__ = [
    "PivotLink",
    "build_pivots",
    "gravatar_url",
    "upscale_avatar",
]


@dataclass
class PivotLink:
    label: str
    url: str
    group: str  # "reverse_image" | "identity" | "dork" | "breach"


class _AccountLike(Protocol):
    username: str
    display_name: str | None
    website: str | None
    profile_image_url: str | None
    raw_data: dict[str, Any] | None


def _q(s: str) -> str:
    return quote(s, safe="")


def upscale_avatar(url: str | None) -> str | None:
    """Swap a Twitter ``_normal`` avatar for the larger ``_400x400`` variant.

    Low-res thumbnails reverse-search poorly; the larger crop is the same image
    at usable resolution. Non-Twitter URLs pass through unchanged.
    """
    if not url:
        return url
    return url.replace("_normal.", "_400x400.")


def gravatar_url(email: str) -> str:
    """Gravatar profile URL for an email (md5 of the normalised address).

    md5 here is Gravatar's required addressing scheme, not a security primitive.
    """
    digest = hashlib.md5(
        email.strip().lower().encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return f"https://www.gravatar.com/{digest}"


def reverse_image_links(image_url: str | None) -> list[PivotLink]:
    if not image_url:
        return []
    enc = _q(upscale_avatar(image_url) or image_url)
    return [
        PivotLink("Google Lens", f"https://lens.google.com/uploadbyurl?url={enc}", "reverse_image"),
        PivotLink("Yandex", f"https://yandex.com/images/search?rpt=imageview&url={enc}", "reverse_image"),
        PivotLink("TinEye", f"https://tineye.com/search?url={enc}", "reverse_image"),
        PivotLink(
            "Bing",
            f"https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&q=imgurl:{enc}",
            "reverse_image",
        ),
    ]


def identity_links(
    handle: str,
    display_name: str | None,
    emails: list[str],
    website: str | None,
) -> list[PivotLink]:
    links: list[PivotLink] = [
        PivotLink(
            "Wayback Machine",
            f"https://web.archive.org/web/*/https://x.com/{_q(handle)}",
            "identity",
        ),
        PivotLink(
            f'Google: "@{handle}" off-X',
            "https://www.google.com/search?q="
            + _q(f'"{handle}" -site:x.com -site:twitter.com'),
            "dork",
        ),
    ]
    if display_name:
        links.append(
            PivotLink(
                f'Google: "{display_name}"',
                "https://www.google.com/search?q=" + _q(f'"{display_name}"'),
                "dork",
            )
        )
    if website:
        url = website if website.startswith("http") else f"https://{website}"
        links.append(PivotLink("Website", url, "identity"))
    for email in emails:
        links.append(PivotLink(f"Gravatar · {email}", gravatar_url(email), "identity"))
        links.append(
            PivotLink(
                f'Google · {email}',
                "https://www.google.com/search?q=" + _q(f'"{email}"'),
                "dork",
            )
        )
    return links


def breach_links(emails: list[str]) -> list[PivotLink]:
    out: list[PivotLink] = []
    for email in emails:
        enc = _q(email)
        out.append(PivotLink(f"Dehashed · {email}", f"https://dehashed.com/search?query={enc}", "breach"))
        out.append(PivotLink(f"Intelligence X · {email}", f"https://intelx.io/?s={enc}", "breach"))
    if emails:
        # HIBP dropped per-email deep links for privacy — link the search page.
        out.append(
            PivotLink("HaveIBeenPwned (paste email)", "https://haveibeenpwned.com/", "breach")
        )
    return out


def build_pivots(account: _AccountLike) -> list[PivotLink]:
    """Assemble every pivot link available for an account record."""
    emails = list((account.raw_data or {}).get("emails") or [])
    return [
        *reverse_image_links(account.profile_image_url),
        *identity_links(account.username, account.display_name, emails, account.website),
        *breach_links(emails),
    ]
