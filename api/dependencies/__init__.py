from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from graph.backends.base import AbstractGraphBackend


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session; commit on success, rollback on exception."""
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_graph(request: Request) -> AbstractGraphBackend:
    return request.app.state.graph


def _check_api_key(request: Request) -> None:
    api_key: str | None = request.app.state.api_key
    if api_key is None:
        return
    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if provided != api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


DbSession = Annotated[AsyncSession, Depends(get_session)]
GraphBackend = Annotated[AbstractGraphBackend, Depends(get_graph)]
ApiKeyCheck = Annotated[None, Depends(_check_api_key)]
