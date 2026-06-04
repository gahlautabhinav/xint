from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import storage.models  # noqa: F401 — side-effect import registers all models

# Import Base so all ORM models register on Base.metadata via their modules
from storage.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """Strip async driver suffixes so Alembic can use a synchronous engine.

    Alembic autogenerate runs synchronously; aiosqlite / asyncpg cannot be
    used in env.py. We swap them out here before handing the URL to SQLAlchemy.
    """
    url = re.sub(r"\+aiosqlite", "", url)
    url = re.sub(r"\+asyncpg", "+psycopg2", url)
    return url


def _get_url() -> str:
    # Prefer explicit alembic config (set_main_option / alembic.ini) over env var.
    # This lets tests pass a custom URL via Config.set_main_option("sqlalchemy.url", ...)
    ini_url = config.get_main_option("sqlalchemy.url") or ""
    raw = ini_url if ini_url.strip() else os.environ.get("DATABASE_URL", "sqlite:///./data/xint.db")
    return _sync_url(raw)


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    ini_section = config.get_section(config.config_ini_section, {})
    ini_section["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
