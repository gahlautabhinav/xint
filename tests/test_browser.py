from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.browser.page import human_delay, safe_goto, scroll_page, wait_for_selector
from scraper.browser.pool import BrowserConfig, BrowserPool

# ---------------------------------------------------------------------------
# human_delay
# ---------------------------------------------------------------------------


class TestHumanDelay:
    async def test_delay_within_range(self):
        calls = []
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock(side_effect=calls.append)):
            await human_delay(200, 800)
        assert calls, "sleep must be called"
        secs = calls[0]
        assert 0.2 <= secs <= 0.8

    async def test_delay_zero_range(self):
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await human_delay(500, 500)
        mock_sleep.assert_called_once()
        secs = mock_sleep.call_args[0][0]
        assert abs(secs - 0.5) < 1e-9

    async def test_delay_never_negative(self):
        recorded = []
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock(side_effect=recorded.append)):
            for _ in range(20):
                await human_delay(0, 1000)
        assert all(s >= 0 for s in recorded)


# ---------------------------------------------------------------------------
# safe_goto
# ---------------------------------------------------------------------------


class TestSafeGoto:
    async def test_success_first_attempt(self):
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        result = await safe_goto(page, "https://x.com", retries=3)
        assert result is True
        page.goto.assert_called_once()

    async def test_retry_on_exception(self):
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=[Exception("timeout"), None])
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock()):
            result = await safe_goto(page, "https://x.com", retries=3)
        assert result is True
        assert page.goto.call_count == 2

    async def test_returns_false_after_max_retries(self):
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("timeout"))
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock()):
            result = await safe_goto(page, "https://x.com", retries=3)
        assert result is False
        assert page.goto.call_count == 3

    async def test_no_sleep_on_last_attempt(self):
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("err"))
        sleep_calls: list = []
        with patch(
            "scraper.browser.page.asyncio.sleep",
            new=AsyncMock(side_effect=sleep_calls.append),
        ):
            await safe_goto(page, "https://x.com", retries=2)
        # retries=2: attempt 0 fails→sleep, attempt 1 fails→NO sleep
        assert len(sleep_calls) == 1

    async def test_passes_wait_until(self):
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        await safe_goto(page, "https://x.com", wait_until="networkidle")
        _, kwargs = page.goto.call_args
        assert kwargs["wait_until"] == "networkidle"


# ---------------------------------------------------------------------------
# scroll_page
# ---------------------------------------------------------------------------


class TestScrollPage:
    async def test_calls_evaluate_n_times(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock()):
            await scroll_page(page, steps=4, pixel_step=600)
        assert page.evaluate.call_count == 4

    async def test_zero_steps_no_evaluate(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        await scroll_page(page, steps=0)
        page.evaluate.assert_not_called()

    async def test_single_step_no_inter_sleep(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        sleep_mock = AsyncMock()
        with patch("scraper.browser.page.asyncio.sleep", new=sleep_mock):
            await scroll_page(page, steps=1, step_delay_ms=500)
        # last step never sleeps
        sleep_mock.assert_not_called()

    async def test_offset_positive(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        with patch("scraper.browser.page.asyncio.sleep", new=AsyncMock()):
            await scroll_page(page, steps=1, pixel_step=600)
        # call_args[0] is the positional-args tuple: (js_string, offset_value)
        pos_args = page.evaluate.call_args[0]
        offset = pos_args[1]
        assert offset > 0


# ---------------------------------------------------------------------------
# wait_for_selector
# ---------------------------------------------------------------------------


class TestWaitForSelector:
    async def test_returns_true_on_success(self):
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=MagicMock())
        result = await wait_for_selector(page, '[data-testid="UserName"]')
        assert result is True

    async def test_returns_false_on_timeout(self):
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        page = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError("timed out"))
        result = await wait_for_selector(page, '[data-testid="missing"]')
        assert result is False

    async def test_propagates_non_timeout_exception(self):
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("unexpected"))
        with pytest.raises(Exception, match="unexpected"):
            await wait_for_selector(page, "selector")


# ---------------------------------------------------------------------------
# BrowserPool
# ---------------------------------------------------------------------------


def _make_mock_playwright_stack():
    """Return (mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap_result)."""
    mock_page = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    mock_ctx.set_default_timeout = MagicMock()
    mock_ctx.set_default_navigation_timeout = MagicMock()
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)
    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_ap_result = MagicMock()
    mock_ap_result.start = AsyncMock(return_value=mock_playwright)
    return mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap_result


class TestBrowserPool:
    async def test_raises_before_start(self):
        pool = BrowserPool()
        with pytest.raises(RuntimeError, match="not started"):
            await pool.new_page()

    async def test_start_launches_browser(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
        mock_playwright.chromium.launch.assert_called_once()

    async def test_new_page_creates_context_and_page(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
            page = await pool.new_page()

        assert page is mock_page
        mock_browser.new_context.assert_called_once()
        mock_ctx.new_page.assert_called_once()

    async def test_proxy_url_passed_to_context(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
            await pool.new_page(proxy_url="http://1.2.3.4:8080")

        _, kwargs = mock_browser.new_context.call_args
        assert kwargs["proxy"] == {"server": "http://1.2.3.4:8080"}

    async def test_no_proxy_key_when_no_proxy(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
            await pool.new_page()

        _, kwargs = mock_browser.new_context.call_args
        assert "proxy" not in kwargs

    async def test_storage_state_loaded_when_file_exists(self, tmp_path):
        state_file = tmp_path / "twitter_state.json"
        state_file.write_text("{}", encoding="utf-8")
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool(BrowserConfig(storage_state_path=str(state_file)))
            await pool.start()
            await pool.new_page()

        _, kwargs = mock_browser.new_context.call_args
        assert kwargs["storage_state"] == str(state_file)

    async def test_no_storage_state_when_file_missing(self, tmp_path):
        missing = tmp_path / "nope.json"
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool(BrowserConfig(storage_state_path=str(missing)))
            await pool.start()
            await pool.new_page()

        _, kwargs = mock_browser.new_context.call_args
        assert "storage_state" not in kwargs

    async def test_close_page_releases_semaphore(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        mock_page.context = mock_ctx
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool(BrowserConfig(max_contexts=1))
            await pool.start()

            assert pool._sem is not None
            page = await pool.new_page()
            assert pool._sem._value == 0  # slot taken

            await pool.close_page(page)
            assert pool._sem._value == 1  # slot released

    async def test_context_manager(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            async with BrowserPool() as pool:
                assert pool._browser is not None

        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    async def test_page_context_releases_on_exit(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        mock_page.context = mock_ctx
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool(BrowserConfig(max_contexts=1))
            await pool.start()
            assert pool._sem is not None

            async with pool.page_context() as page:
                assert pool._sem._value == 0
                assert page is mock_page

            assert pool._sem._value == 1  # released on exit

    async def test_stop_is_idempotent(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
            await pool.stop()
            assert pool._browser is None
            await pool.stop()  # must not raise

    async def test_stealth_applied_to_context(self):
        mock_page, mock_ctx, mock_browser, mock_playwright, mock_ap = (
            _make_mock_playwright_stack()
        )
        with (
            patch("scraper.browser.pool.async_playwright", return_value=mock_ap),
            patch("scraper.browser.pool._stealth") as mock_stealth,
        ):
            mock_stealth.apply_stealth_async = AsyncMock()
            pool = BrowserPool()
            await pool.start()
            await pool.new_page()

        mock_stealth.apply_stealth_async.assert_called_once_with(mock_ctx)


# ---------------------------------------------------------------------------
# Session cookie import (scraper.auth.save_session_from_cookies)
# ---------------------------------------------------------------------------


class TestCookieImport:
    def test_builds_storage_state(self, tmp_path):
        from scraper import auth

        dest = tmp_path / "twitter_state.json"
        with patch("scraper.auth.twitter_session_path", return_value=dest):
            path = auth.save_session_from_cookies("AUTHTOK", "CSRFTOK")

        assert path == dest
        data = json.loads(dest.read_text(encoding="utf-8"))
        names = {c["name"] for c in data["cookies"]}
        assert names == {"auth_token", "ct0"}
        # auth_token carries the supplied value on the x.com domain
        x_auth = [
            c
            for c in data["cookies"]
            if c["name"] == "auth_token" and c["domain"] == ".x.com"
        ]
        assert len(x_auth) == 1
        assert x_auth[0]["value"] == "AUTHTOK"

    def test_requires_both_cookies(self, tmp_path):
        from scraper import auth

        with (
            patch("scraper.auth.twitter_session_path", return_value=tmp_path / "s.json"),
            pytest.raises(ValueError),
        ):
            auth.save_session_from_cookies("", "ct0")
