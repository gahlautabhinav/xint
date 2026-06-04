from __future__ import annotations

import logging
from dataclasses import dataclass, field

from playwright.async_api import Page

from scraper.browser.page import human_delay, safe_goto, wait_for_selector
from scraper.extractors.cross_platform import extract_all_links
from scraper.extractors.twitter import ProfileData, TweetData, extract_profile, extract_tweets
from scraper.ratelimit.profiles import RateProfile
from scraper.ratelimit.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

_PROFILE_SELECTOR = '[data-testid="UserName"]'
_TWITTER_BASE_URL = "https://x.com"
_EMPTY_PROFILE = ProfileData(handle=None, display_name=None, bio=None, website=None)


@dataclass
class ScrapeResult:
    username: str
    profile: ProfileData
    tweets: list[TweetData] = field(default_factory=list)
    cross_platform: dict[str, str] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


async def scrape_account(
    page: Page,
    username: str,
    *,
    bucket: TokenBucket,
    rate_profile: RateProfile,
) -> ScrapeResult:
    """Scrape a single Twitter profile page and return extracted data.

    Acquires a rate-limit token before navigating. Returns a failed
    ScrapeResult (success=False) on navigation errors or missing DOM, rather
    than raising — callers decide whether to retry or skip.
    """
    url = f"{_TWITTER_BASE_URL}/{username}"

    await bucket.acquire()
    try:
        ok = await safe_goto(page, url, timeout_ms=30_000)
        if not ok:
            return ScrapeResult(
                username=username, profile=_EMPTY_PROFILE, success=False, error="navigation failed"
            )

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
        tweets = await extract_tweets(page)
    except Exception as exc:
        logger.warning("scrape_account(%r) error: %s", username, exc)
        return ScrapeResult(
            username=username, profile=_EMPTY_PROFILE, success=False, error=str(exc)
        )

    texts = [t for t in [profile.bio, profile.website] if t is not None]
    texts += [tw.text for tw in tweets]
    cross_platform = extract_all_links(texts)

    return ScrapeResult(
        username=username,
        profile=profile,
        tweets=tweets,
        cross_platform=cross_platform,
        success=True,
    )
