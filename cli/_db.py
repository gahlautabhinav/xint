from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


async def setup_db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create engine + session factory from settings. Auto-creates tables."""
    from config.settings import get_settings
    from storage.base import Base
    from storage.engine import create_engine_from_settings
    from storage.session import create_session_factory

    settings = get_settings()
    engine = create_engine_from_settings(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, create_session_factory(engine)
