from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import accounts, graph, jobs
from config.settings import get_settings
from graph.backends.neo4j_backend import Neo4jBackend
from graph.backends.networkx_backend import NetworkxBackend
from storage.base import Base
from storage.engine import create_engine_from_settings
from storage.session import create_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    settings = get_settings()

    engine = create_engine_from_settings(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.session_factory = create_session_factory(engine)

    if settings.GRAPH_BACKEND == "neo4j":
        backend: Any = Neo4jBackend(
            url=settings.NEO4J_URL,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
        )
        await backend.connect()
    else:
        backend = NetworkxBackend()
    app.state.graph = backend
    app.state.api_key = settings.API_KEY

    logger.info("Startup complete — DB: %s, graph: %s", settings.DATABASE_URL, settings.GRAPH_BACKEND)

    yield

    await engine.dispose()
    if settings.GRAPH_BACKEND == "neo4j":
        await backend.close()

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="TwitterOSINT API",
        description="OSINT network graph API for Twitter/X accounts",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router)
    app.include_router(accounts.router)
    app.include_router(graph.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
