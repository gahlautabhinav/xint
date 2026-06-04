from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the given engine.

    ``expire_on_commit=False`` keeps ORM objects usable after commit without
    requiring an extra round-trip to reload them — safe for our single-writer
    async pattern.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Async generator that yields a session and handles rollback on error.

    Intended for use with FastAPI ``Depends`` or manual ``async with`` usage::

        async for session in get_session(factory):
            ...
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
