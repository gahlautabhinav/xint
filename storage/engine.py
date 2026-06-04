from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.settings import Settings


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Create an async SQLAlchemy engine configured for the given settings.

    SQLite engines are configured with WAL mode and NORMAL synchronous writes
    for safe concurrent reads while keeping single-writer performance.
    Postgres engines use a connection pool with pre-ping health checks.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        engine = create_async_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def set_wal(dbapi_conn: object, connection_record: object) -> None:  # noqa: ARG001
            cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

        return engine

    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
