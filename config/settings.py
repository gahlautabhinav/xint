from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/osint.db"

    # Graph backend
    GRAPH_BACKEND: Literal["neo4j", "networkx"] = "networkx"
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Scraper
    BROWSER_POOL_SIZE: int = Field(default=3, ge=1, le=10)
    RATE_PROFILE: Literal["conservative", "moderate", "aggressive"] = "moderate"
    DEFAULT_DEPTH: int = Field(default=2, ge=1, le=4)
    DEFAULT_MAX_ACCOUNTS: int = Field(default=500, ge=1, le=10000)
    SELECTOR_VERSION: str = "v1"

    # Proxy
    PROXY_FILE: str = "config/proxies.txt"
    PROXY_REFRESH_ON_STARTUP: bool = False
    PROXY_MIN_POOL_SIZE: int = 5

    # Sessions
    SESSION_DIR: str = "config/sessions"

    # Anti-detection
    UA_POOL_FILE: str = "config/ua_pool.txt"
    HUMAN_DELAY_MIN_MS: int = 2000
    HUMAN_DELAY_MAX_MS: int = 8000

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_KEY: str | None = None

    # Data
    DATA_DIR: str = "./data"
    MAX_RAW_DATA_AGE_DAYS: int = 30

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str | None = None


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
