from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from scraper.session import twitter_session_path

logger = logging.getLogger(__name__)

LOGIN_URL = "https://x.com/login"

_PROMPT = (
    "\nA browser window has opened. Log in to X/Twitter there, "
    "then press Enter here to save the session… "
)


async def save_login_session(headless: bool = False) -> Path:
    """Open a browser, let the user log in to X, and persist the session.

    Saves a Playwright ``storage_state`` (cookies + localStorage) to
    :func:`scraper.session.twitter_session_path`. Subsequent crawls load it so
    scraping runs authenticated.

    Runs the browser on the caller's event loop, so call it from a context with
    a subprocess-capable loop (the CLI's ``asyncio.run`` uses a ProactorEventLoop
    on Windows, which is correct).
    """
    from playwright.async_api import async_playwright

    path = twitter_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001 — navigation hiccup shouldn't abort login
            logger.warning("Could not open %s automatically: %s", LOGIN_URL, exc)

        # Block on user confirmation without freezing the Playwright connection.
        await asyncio.to_thread(input, _PROMPT)

        await context.storage_state(path=str(path))
        await browser.close()

    logger.info("Saved X session to %s", path)
    return path
