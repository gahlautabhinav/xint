from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings, get_settings


def test_defaults_load():
    s = Settings()
    assert s.DATABASE_URL == "sqlite+aiosqlite:///./data/osint.db"
    assert s.GRAPH_BACKEND == "networkx"
    assert s.BROWSER_POOL_SIZE == 3
    assert s.RATE_PROFILE == "moderate"
    assert s.DEFAULT_DEPTH == 2
    assert s.DEFAULT_MAX_ACCOUNTS == 500
    assert s.API_KEY is None
    assert s.LOG_FILE is None


def test_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost/test"
    assert s.LOG_LEVEL == "DEBUG"


def test_graph_backend_rejects_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRAPH_BACKEND", "redis")
    with pytest.raises(ValidationError):
        Settings()


def test_rate_profile_rejects_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RATE_PROFILE", "turbo")
    with pytest.raises(ValidationError):
        Settings()


def test_browser_pool_size_bounds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BROWSER_POOL_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("BROWSER_POOL_SIZE", "11")
    with pytest.raises(ValidationError):
        Settings()


def test_default_depth_bounds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEFAULT_DEPTH", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("DEFAULT_DEPTH", "5")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_cached():
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()


def test_api_key_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_KEY", "secret-token")
    s = Settings()
    assert s.API_KEY == "secret-token"
