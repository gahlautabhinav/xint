from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx
from playwright.async_api import Page

from scraper.analysis.timezone import infer_timezone
from scraper.browser.page import human_delay, safe_goto, scroll_page, wait_for_selector
from scraper.extractors.cross_platform import extract_all_links, extract_contacts
from scraper.extractors.twitter import (
    ProfileData,
    TweetData,
    extract_following,
    extract_profile,
    extract_tweets,
)
from scraper.ratelimit.profiles import RateProfile
from scraper.ratelimit.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

_TCO_RE = re.compile(r"https?://t\.co/\S+", re.IGNORECASE)


async def _expand_tco(url: str) -> str:
    """Follow a t.co short link and return the final URL. Returns original on failure."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
            r = await client.head(url)
            return str(r.url)
    except Exception:
        return url


async def _expand_tco_in_texts(texts: list[str]) -> list[str]:
    """Replace t.co links in text list with their expanded destinations."""
    expanded = []
    for text in texts:
        matches = _TCO_RE.findall(text)
        for short in matches:
            real = await _expand_tco(short)
            text = text.replace(short, real)
        expanded.append(text)
    return expanded


_PROFILE_SELECTOR = '[data-testid="UserName"]'
_TWEET_SELECTOR = '[data-testid="tweet"]'
_USERCELL_SELECTOR = '[data-testid="UserCell"]'
_TWITTER_BASE_URL = "https://x.com"
_EMPTY_PROFILE = ProfileData(handle=None, display_name=None, bio=None, website=None)


@dataclass
class ScrapeResult:
    username: str
    profile: ProfileData
    tweets: list[TweetData] = field(default_factory=list)
    cross_platform: dict[str, str] = field(default_factory=dict)
    contacts: dict[str, list[str]] = field(default_factory=dict)  # emails, phones
    activity: dict[str, object] | None = None  # timezone/posting-hour estimate
    following: list[str] = field(default_factory=list)
    followers: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


async def _scrape_user_list(
    page: Page,
    list_url: str,
    *,
    bucket: TokenBucket,
    max_count: int,
) -> list[str]:
    """Navigate to a following/followers list URL and collect handles."""
    await bucket.acquire()
    ok = await safe_goto(page, list_url, timeout_ms=30_000)
    if not ok or not await wait_for_selector(page, _USERCELL_SELECTOR, timeout_ms=10_000):
        return []
    return await extract_following(page, max_count=max_count)


async def scrape_account(
    page: Page,
    username: str,
    *,
    bucket: TokenBucket,
    rate_profile: RateProfile,
    scrape_following: bool = False,
    max_following: int = 50,
    scrape_followers: bool = False,
    max_followers: int = 50,
) -> ScrapeResult:
    """Scrape a single Twitter profile page and return extracted data.

    Acquires a rate-limit token before navigating. Returns a failed
    ScrapeResult (success=False) on navigation errors or missing DOM, rather
    than raising — callers decide whether to retry or skip.

    When *scrape_following* / *scrape_followers* are set, also visits
    ``/<user>/following`` and ``/<user>/followers`` and collects up to
    *max_following* / *max_followers* handles (the network edges — most
    accounts don't @mention the people they follow).
    """
    # /with_replies includes both original tweets and replies in one scroll,
    # giving the bias agent full context instead of tweets-only.
    url = f"{_TWITTER_BASE_URL}/{username}/with_replies"

    await bucket.acquire()
    try:
        ok = await safe_goto(page, url, timeout_ms=30_000)
        if not ok:
            return ScrapeResult(
                username=username, profile=_EMPTY_PROFILE, success=False, error="navigation failed"
            )

        found = await wait_for_selector(page, _PROFILE_SELECTOR, timeout_ms=10_000)
        if not found:
            # /with_replies may not render for suspended/private accounts — retry base URL
            await bucket.acquire()
            ok2 = await safe_goto(page, f"{_TWITTER_BASE_URL}/{username}", timeout_ms=30_000)
            if ok2:
                found = await wait_for_selector(page, _PROFILE_SELECTOR, timeout_ms=10_000)
        if not found:
            return ScrapeResult(
                username=username,
                profile=_EMPTY_PROFILE,
                success=False,
                error="profile selector not found",
            )

        await human_delay(rate_profile.human_delay_min_ms, rate_profile.human_delay_max_ms)
        profile = await extract_profile(page)

        # The timeline loads after the profile header — wait for the first tweet
        # then scroll to pull a batch so mention/reply edges aren't missed.
        await wait_for_selector(page, _TWEET_SELECTOR, timeout_ms=8_000)
        await scroll_page(page, steps=3)
        tweets = await extract_tweets(page)
    except Exception as exc:
        logger.warning("scrape_account(%r) error: %s", username, exc)
        return ScrapeResult(
            username=username, profile=_EMPTY_PROFILE, success=False, error=str(exc)
        )

    following: list[str] = []
    if scrape_following:
        try:
            following = await _scrape_user_list(
                page, f"{url}/following", bucket=bucket, max_count=max_following
            )
        except Exception as exc:
            logger.warning("scrape_account(%r) following error: %s", username, exc)

    followers: list[str] = []
    if scrape_followers:
        try:
            followers = await _scrape_user_list(
                page, f"{url}/followers", bucket=bucket, max_count=max_followers
            )
        except Exception as exc:
            logger.warning("scrape_account(%r) followers error: %s", username, exc)

    raw_texts = [t for t in [profile.bio, profile.website] if t is not None]
    raw_texts += [tw.text for tw in tweets]

    # Expand t.co short links so cross-platform + contact detection works on real URLs
    texts = await _expand_tco_in_texts(raw_texts)

    cross_platform = extract_all_links(texts)
    contacts = extract_contacts(texts)

    # Infer posting timezone from tweet timestamps (heuristic OSINT signal).
    activity = infer_timezone([tw.timestamp for tw in tweets]).to_dict()

    return ScrapeResult(
        username=username,
        profile=profile,
        tweets=tweets,
        cross_platform=cross_platform,
        contacts=contacts,
        activity=activity,
        following=following,
        followers=followers,
        success=True,
    )
