from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_HASHTAG_RE = re.compile(r"#(\w+)")
_MENTION_RE = re.compile(r"@(\w{1,50})")
_COUNT_HEAD_RE = re.compile(r"^([\d,.]+[KMBkmb]?)")


def _parse_count(text: str | None) -> int | None:
    """Parse Twitter abbreviated counts: '1.2K' → 1200, '3.4M' → 3_400_000."""
    if not text:
        return None
    text = text.strip()
    m = _COUNT_HEAD_RE.match(text)
    if not m:
        return None
    val = m.group(1).replace(",", "")
    try:
        if val[-1].upper() == "K":
            return int(float(val[:-1]) * 1_000)
        if val[-1].upper() == "M":
            return int(float(val[:-1]) * 1_000_000)
        if val[-1].upper() == "B":
            return int(float(val[:-1]) * 1_000_000_000)
        return int(float(val))
    except (ValueError, IndexError):
        return None


@dataclass
class ProfileData:
    handle: str | None
    display_name: str | None
    bio: str | None
    website: str | None
    follower_count: int | None = None
    following_count: int | None = None
    is_verified: bool = False


@dataclass
class TweetData:
    tweet_id: str | None
    text: str
    timestamp: str | None
    mentions: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    reply_to: str | None = None
    quote_url: str | None = None


# ---------------------------------------------------------------------------
# JS snippets — evaluated in the page context
# ---------------------------------------------------------------------------

_PROFILE_JS = """
() => {
    const tid = id => document.querySelector('[data-testid="' + id + '"]');
    const text = id => { const el = tid(id); return el ? el.innerText.trim() : null; };

    const nameEl = tid('UserName');
    let handle = null, display_name = null;
    if (nameEl) {
        const spans = Array.from(nameEl.querySelectorAll('span'));
        for (const s of spans) {
            const t = s.innerText.trim();
            if (!t || t.length <= 1) continue;
            if (t.startsWith('@') && !handle) { handle = t.slice(1); }
            else if (!t.startsWith('@') && !display_name) { display_name = t; }
        }
    }

    const statLinks = Array.from(
        document.querySelectorAll('a[href$="/following"], a[href$="/followers"]')
    );
    let following_raw = null, followers_raw = null;
    for (const a of statLinks) {
        const href = a.getAttribute('href') || '';
        const span = a.querySelector('span');
        const val = span ? span.innerText.trim() : null;
        if (href.endsWith('/following') && !following_raw) following_raw = val;
        if (href.endsWith('/followers') && !followers_raw) followers_raw = val;
    }

    return {
        handle,
        display_name,
        bio: text('UserDescription'),
        website: text('UserUrl'),
        followers_raw,
        following_raw,
        is_verified: !!document.querySelector('[data-testid="icon-verified"]'),
    };
}
"""

_TWEETS_JS = r"""
() => {
    return Array.from(document.querySelectorAll('[data-testid="tweet"]')).map(tw => {
        const textEl = tw.querySelector('[data-testid="tweetText"]');
        const text = textEl ? textEl.innerText.trim() : '';

        const timeEl = tw.querySelector('time');
        const link = timeEl ? timeEl.closest('a') : null;
        const href = link ? link.getAttribute('href') : null;
        const idM = href ? href.match(/\/status\/(\d+)/) : null;

        const quoteEl = tw.querySelector('[data-testid="quoteTweet"]');
        const quoteLink = quoteEl ? quoteEl.querySelector('a[href*="/status/"]') : null;

        const socialCtx = tw.querySelector('[data-testid="socialContext"]');
        const replyM = socialCtx ? socialCtx.innerText.match(/@(\w+)/) : null;

        return {
            tweet_id: idM ? idM[1] : null,
            text,
            timestamp: timeEl ? timeEl.getAttribute('datetime') : null,
            quote_url: quoteLink ? quoteLink.getAttribute('href') : null,
            reply_to: replyM ? replyM[1] : null,
        };
    });
}
"""


async def extract_profile(page: Page) -> ProfileData:
    """Extract profile data from a Twitter profile page via DOM evaluation."""
    try:
        raw: dict[str, Any] = await page.evaluate(_PROFILE_JS)
    except Exception as exc:
        logger.warning("extract_profile evaluate failed: %s", exc)
        return ProfileData(handle=None, display_name=None, bio=None, website=None)

    return ProfileData(
        handle=raw.get("handle"),
        display_name=raw.get("display_name"),
        bio=raw.get("bio"),
        website=raw.get("website"),
        follower_count=_parse_count(raw.get("followers_raw")),
        following_count=_parse_count(raw.get("following_raw")),
        is_verified=bool(raw.get("is_verified", False)),
    )


async def extract_tweets(page: Page) -> list[TweetData]:
    """Extract visible tweets from a Twitter timeline page via DOM evaluation."""
    try:
        raw_list: list[dict[str, Any]] = await page.evaluate(_TWEETS_JS)
    except Exception as exc:
        logger.warning("extract_tweets evaluate failed: %s", exc)
        return []

    tweets: list[TweetData] = []
    for raw in raw_list:
        text = raw.get("text", "")
        tweets.append(
            TweetData(
                tweet_id=raw.get("tweet_id"),
                text=text,
                timestamp=raw.get("timestamp"),
                mentions=_MENTION_RE.findall(text),
                hashtags=_HASHTAG_RE.findall(text),
                reply_to=raw.get("reply_to"),
                quote_url=raw.get("quote_url"),
            )
        )
    return tweets


def extract_mentions_from_text(text: str) -> list[str]:
    """Extract @handles from raw text. Pure function — no page needed."""
    return _MENTION_RE.findall(text)


def extract_hashtags_from_text(text: str) -> list[str]:
    """Extract #tags from raw text. Pure function — no page needed."""
    return _HASHTAG_RE.findall(text)
