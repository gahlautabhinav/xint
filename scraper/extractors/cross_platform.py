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
}


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
