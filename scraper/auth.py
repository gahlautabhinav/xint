from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from scraper.session import twitter_session_path

logger = logging.getLogger(__name__)

LOGIN_URL = "https://x.com/login"

_PROMPT = (
    "\nA browser window has opened. Log in to X/Twitter there, "
    "then press Enter here to save the session… "
)

# Anti-automation launch tweaks — make the controlled browser look less like a bot.
_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]
_IGNORE_DEFAULT_ARGS = ["--enable-automation"]

# X session is carried by these two cookies. auth_token is the auth credential
# (httpOnly); ct0 is the CSRF token. Both are read by the API on every request.
_COOKIE_DOMAINS = (".x.com", ".twitter.com")


def save_session_from_cookies(auth_token: str, ct0: str) -> Path:
    """Build a Playwright storage_state from X session cookies and save it.

    This never automates the login form, so it sidesteps X's "we've temporarily
    limited your login" anti-bot wall entirely. Grab the cookies from a browser
    where you're already logged in (DevTools → Application → Cookies → x.com).

    Returns the path the session was written to.
    """
    auth_token = auth_token.strip()
    ct0 = ct0.strip()
    if not auth_token or not ct0:
        raise ValueError("Both auth_token and ct0 cookies are required.")

    cookies: list[dict[str, object]] = []
    for domain in _COOKIE_DOMAINS:
        cookies.append(
            {
                "name": "auth_token",
                "value": auth_token,
                "domain": domain,
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        )
        cookies.append(
            {
                "name": "ct0",
                "value": ct0,
                "domain": domain,
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )

    state = {"cookies": cookies, "origins": []}
    path = twitter_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    logger.info("Saved X session (cookie import) to %s", path)
    return path


async def save_login_session(headless: bool = False) -> Path:
    """Open a browser, let the user log in to X, and persist the session.

    Saves a Playwright ``storage_state`` (cookies + localStorage) to
    :func:`scraper.session.twitter_session_path`.

    Launches real Chrome (``channel="chrome"``) with automation flags stripped
    when available — X is far more likely to limit a bundled-Chromium login.
    Falls back to bundled Chromium if Chrome isn't installed. Note: X may still
    rate-limit automated logins ("we've temporarily limited your login"); if so,
    use cookie import (:func:`save_session_from_cookies`) instead.

    Runs on the caller's event loop, so call it from a context with a
    subprocess-capable loop (the CLI's ``asyncio.run`` uses a ProactorEventLoop
    on Windows, which is correct).
    """
    from playwright.async_api import async_playwright

    path = twitter_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=headless,
                channel="chrome",
                args=_STEALTH_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
            )
        except Exception as exc:  # noqa: BLE001 — Chrome not installed → use Chromium
            logger.warning("Real Chrome unavailable (%s); falling back to Chromium", exc)
            browser = await pw.chromium.launch(
                headless=headless,
                args=_STEALTH_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
            )

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
