from __future__ import annotations

import re

PLATFORM_PATTERNS: dict[str, re.Pattern[str]] = {
    "instagram": re.compile(
        r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?",
        re.IGNORECASE,
    ),
    "github": re.compile(
        r"(?:https?://)?(?:www\.)?github\.com/"
        r"(?!features|pricing|login|about|contact|explore|marketplace|topics|trending)"
        r"([A-Za-z0-9._-]{1,39})(?:/[^\s]*)?",
        re.IGNORECASE,
    ),
    "linkedin": re.compile(
        r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9._-]{3,30})/?",
        re.IGNORECASE,
    ),
    "tiktok": re.compile(
        r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9._]{2,24})/?",
        re.IGNORECASE,
    ),
    "youtube": re.compile(
        r"(?:https?://)?(?:www\.)?youtube\.com/(?:c/|channel/|@)([A-Za-z0-9._-]{3,50})/?",
        re.IGNORECASE,
    ),
    "telegram": re.compile(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})/?",
        re.IGNORECASE,
    ),
    "discord": re.compile(
        r"(?:https?://)?(?:www\.)?discord(?:\.gg|app\.com/invite|\.com/invite)/([A-Za-z0-9-]{2,32})/?",
        re.IGNORECASE,
    ),
}

# Contact patterns — public info posted by users in bios/tweets
_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
)

# E.164, US, international formats — require enough digits to avoid false positives
_PHONE_RE = re.compile(
    r"(?<!\w)(\+?(?:[\d]{1,3}[\s\-.])?(?:\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{4})(?!\d)",
)

_PHONE_MIN_DIGITS = 7  # filter out things like "2000" or "123-456"


def extract_emails(text: str) -> list[str]:
    """Extract publicly posted email addresses from text."""
    return list(dict.fromkeys(m.lower() for m in _EMAIL_RE.findall(text)))


def extract_phones(text: str) -> list[str]:
    """Extract publicly posted phone numbers from text. Filters short matches."""
    results = []
    seen: set[str] = set()
    for m in _PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if len(digits) < _PHONE_MIN_DIGITS:
            continue
        if m not in seen:
            seen.add(m)
            results.append(m)
    return results


def extract_contacts(texts: list[str]) -> dict[str, list[str]]:
    """Extract emails + phones from a list of text sources (bio, tweets, etc.)."""
    emails: list[str] = []
    phones: list[str] = []
    seen_e: set[str] = set()
    seen_p: set[str] = set()
    for text in texts:
        for e in extract_emails(text):
            if e not in seen_e:
                seen_e.add(e)
                emails.append(e)
        for p in extract_phones(text):
            if p not in seen_p:
                seen_p.add(p)
                phones.append(p)
    return {"emails": emails, "phones": phones}


def extract_cross_platform_links(text: str) -> dict[str, str]:
    """Extract social handles from a text string (bio, tweet, etc.).

    Returns {platform: handle} for each detected platform. First match per
    platform. Returns empty dict if no platforms detected.
    """
    results: dict[str, str] = {}
    for platform, pattern in PLATFORM_PATTERNS.items():
        m = pattern.search(text)
        if m:
            handle = m.group(1).rstrip("/").rstrip(".")
            results[platform] = handle
    return results


def extract_all_links(texts: list[str]) -> dict[str, str]:
    """Merge cross-platform links from multiple text sources.

    First occurrence wins — later texts do not override an already-found platform.
    """
    merged: dict[str, str] = {}
    for text in texts:
        for platform, handle in extract_cross_platform_links(text).items():
            if platform not in merged:
                merged[platform] = handle
    return merged
