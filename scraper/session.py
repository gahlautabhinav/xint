from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import get_settings

if TYPE_CHECKING:
    from scraper.browser.pool import BrowserConfig


def twitter_session_path() -> Path:
    """Filesystem path of the saved X/Twitter login session.

    A Playwright ``storage_state`` JSON (cookies + localStorage) written by
    ``xint login``. Lives under ``SESSION_DIR`` and is gitignored, so the
    credentials never reach version control.
    """
    return Path(get_settings().SESSION_DIR) / "twitter_state.json"


def has_twitter_session() -> bool:
    """True if a saved login session exists on disk."""
    return twitter_session_path().exists()


def authed_browser_config(**overrides: object) -> BrowserConfig:
    """Build a :class:`BrowserConfig` that loads the saved session when present.

    Extra keyword arguments override individual config fields.
    """
    from scraper.browser.pool import BrowserConfig

    path = twitter_session_path()
    state = str(path) if path.exists() else None
    return BrowserConfig(storage_state_path=state, **overrides)  # type: ignore[arg-type]
