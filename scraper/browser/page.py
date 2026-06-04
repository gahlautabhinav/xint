from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from scraper.ratelimit.backoff import full_jitter

logger = logging.getLogger(__name__)


async def human_delay(min_ms: int, max_ms: int) -> None:
    """Sleep a random duration in [min_ms, max_ms] milliseconds."""
    seconds = random.uniform(min_ms, max_ms) / 1000.0
    await asyncio.sleep(seconds)


async def safe_goto(
    page: Page,
    url: str,
    *,
    timeout_ms: int = 30_000,
    retries: int = 3,
    backoff_base: float = 1.0,
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded",
) -> bool:
    """Navigate to url with retries. Returns True on success, False after exhaustion."""
    for attempt in range(retries):
        try:
            await page.goto(url, timeout=timeout_ms, wait_until=wait_until)
            return True
        except Exception as exc:
            logger.debug(
                "goto attempt %d/%d failed for %s: %s", attempt + 1, retries, url, exc
            )
            if attempt < retries - 1:
                wait = full_jitter(attempt, base=backoff_base)
                await asyncio.sleep(wait)
    return False


async def scroll_page(
    page: Page,
    *,
    steps: int = 5,
    step_delay_ms: int = 800,
    pixel_step: int = 600,
) -> None:
    """Human-like incremental scroll with random jitter on each step."""
    for i in range(steps):
        offset = pixel_step + random.randint(-100, 100)
        await page.evaluate("offset => window.scrollBy(0, offset)", offset)
        if i < steps - 1:
            jitter = random.uniform(-0.1, 0.2)
            await asyncio.sleep(max(0.0, step_delay_ms / 1000.0 + jitter))


async def wait_for_selector(
    page: Page,
    selector: str,
    *,
    timeout_ms: int = 10_000,
) -> bool:
    """Wait for selector to appear. Returns True if found, False on timeout."""
    try:
        await page.wait_for_selector(selector, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False
