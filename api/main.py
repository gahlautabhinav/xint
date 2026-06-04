from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.routers import accounts, graph, jobs
from config.settings import get_settings
from graph.backends.base import AbstractGraphBackend
from graph.backends.neo4j_backend import Neo4jBackend
from graph.backends.networkx_backend import NetworkxBackend
from graph.schema.nodes import make_node_id
from storage.base import Base
from storage.engine import create_engine_from_settings
from storage.models.account import Account
from storage.models.relationship import Relationship
from storage.session import create_session_factory

logger = logging.getLogger(__name__)


async def _rebuild_graph(session_factory: async_sessionmaker[AsyncSession], backend: AbstractGraphBackend) -> None:
    """Reload all accounts + relationships from SQLite into the in-memory graph.

    Called on startup so the networkx graph survives API restarts.
    """
    async with session_factory() as session:
        accounts_result = await session.execute(select(Account))
        all_accounts = accounts_result.scalars().all()

        rels_result = await session.execute(select(Relationship))
        all_rels = rels_result.scalars().all()

    account_map: dict[str, Account] = {str(a.id): a for a in all_accounts}

    for acc in all_accounts:
        node_id = make_node_id(acc.platform, acc.username)
        await backend.upsert_node(
            node_id,
            ["Account"],
            {
                "display_name": acc.display_name or "",
                "bio": acc.bio or "",
                "followers_count": acc.followers_count or 0,
                "is_verified": acc.is_verified or False,
                "scrape_depth": acc.scrape_depth or 0,
            },
        )

    for rel in all_rels:
        src_acc = account_map.get(str(rel.source_account_id))
        dst_acc = account_map.get(str(rel.target_account_id))
        if src_acc and dst_acc:
            src_id = make_node_id(src_acc.platform, src_acc.username)
            dst_id = make_node_id(dst_acc.platform, dst_acc.username)
            await backend.upsert_edge(src_id, dst_id, rel.rel_type.value, {"weight": 1.0})

    logger.info("Graph rebuilt from DB: %d nodes, %d edges", len(all_accounts), len(all_rels))


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

    if settings.GRAPH_BACKEND == "networkx":
        await _rebuild_graph(app.state.session_factory, backend)

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
