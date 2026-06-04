from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright

try:
    from playwright_stealth import Stealth as _Stealth

    _stealth: _Stealth | None = _Stealth()
except ImportError:
    _stealth = None

logger = logging.getLogger(__name__)

_FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _random_ua() -> str:
    try:
        from fake_useragent import UserAgent  # noqa: PLC0415

        return UserAgent().random
    except Exception:
        return _FALLBACK_UA


@dataclass
class BrowserConfig:
    headless: bool = True
    max_contexts: int = 3
    default_timeout_ms: int = 30_000
    viewport_width: int = 1280
    viewport_height: int = 720
    # Path to a Playwright storage_state JSON (cookies + localStorage) saved by
    # `xint login`. When set and present, every context loads it so scraping is
    # authenticated. None / missing file → anonymous (logged-out) scraping.
    storage_state_path: str | None = None


class BrowserPool:
    """Pool of isolated Playwright contexts with stealth + UA rotation.

    Each call to new_page() creates a fresh BrowserContext (isolated cookies/session)
    and applies playwright-stealth. Semaphore caps concurrent in-flight contexts.
    Prefer page_context() over raw new_page() to guarantee semaphore release.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self._config = config or BrowserConfig()
        self._sem: asyncio.Semaphore | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """Launch Playwright + Chromium. Must be called before new_page()."""
        self._sem = asyncio.Semaphore(self._config.max_contexts)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._config.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # Hide the automation flag so X is less likely to gate content.
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        logger.info(
            "BrowserPool started (headless=%s, max_contexts=%d)",
            self._config.headless,
            self._config.max_contexts,
        )

    async def stop(self) -> None:
        """Close browser + Playwright runtime. Idempotent."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("BrowserPool stopped")

    async def new_page(self, proxy_url: str | None = None) -> Page:
        """Acquire a semaphore slot, create a stealth context+page.

        Raises RuntimeError if start() was not called.
        Caller MUST call close_page() to release the slot.
        Prefer page_context() for automatic cleanup.
        """
        if self._sem is None or self._browser is None:
            raise RuntimeError("BrowserPool not started — call start() first")

        await self._sem.acquire()
        try:
            ctx_opts: dict[str, Any] = {
                "user_agent": _random_ua(),
                "viewport": {
                    "width": self._config.viewport_width,
                    "height": self._config.viewport_height,
                },
            }
            if proxy_url:
                ctx_opts["proxy"] = {"server": proxy_url}
            # Load a saved login session so scraping is authenticated.
            state_path = self._config.storage_state_path
            if state_path and Path(state_path).exists():
                ctx_opts["storage_state"] = state_path

            ctx = await self._browser.new_context(**ctx_opts)
            ctx.set_default_timeout(self._config.default_timeout_ms)
            ctx.set_default_navigation_timeout(self._config.default_timeout_ms)
            if _stealth is not None:
                await _stealth.apply_stealth_async(ctx)
            page = await ctx.new_page()
            return page
        except Exception:
            self._sem.release()
            raise

    async def close_page(self, page: Page) -> None:
        """Close page + its context, release the semaphore slot."""
        try:
            ctx = page.context
            await page.close()
            await ctx.close()
        finally:
            if self._sem:
                self._sem.release()

    @asynccontextmanager
    async def page_context(self, proxy_url: str | None = None) -> AsyncIterator[Page]:
        """Context manager that guarantees close_page() on exit.

        Usage: async with pool.page_context() as page: ...
        """
        page = await self.new_page(proxy_url)
        try:
            yield page
        finally:
            await self.close_page(page)

    async def __aenter__(self) -> BrowserPool:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()
