from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import storage.models  # noqa: F401 — registers all models with Base
from api.main import create_app
from graph.backends.networkx_backend import NetworkxBackend
from storage.base import Base
from storage.models.job import JobStatus
from storage.repositories.job_repo import JobRepository


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def graph_backend():
    return NetworkxBackend()


@pytest.fixture
def app(session_factory, graph_backend):
    application = create_app()
    application.state.session_factory = session_factory
    application.state.graph = graph_backend
    application.state.api_key = None
    return application


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_analyze_now_returns_202(client, session_factory):
    mock_thread = MagicMock()
    with (
        patch("api.routers.jobs.threading.Thread", return_value=mock_thread),
        patch("api.routers.jobs.run_crawl_in_thread"),
    ):
        resp = await client.post("/jobs/analyze-now", json={"username": "testuser"})

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["username"] == "testuser"
    uuid.UUID(data["job_id"])  # raises if invalid


@pytest.mark.asyncio
async def test_analyze_now_creates_pending_job(client, session_factory):
    mock_thread = MagicMock()
    with (
        patch("api.routers.jobs.threading.Thread", return_value=mock_thread),
        patch("api.routers.jobs.run_crawl_in_thread"),
    ):
        resp = await client.post("/jobs/analyze-now", json={"username": "testuser"})

    assert resp.status_code == 202
    job_id = uuid.UUID(resp.json()["job_id"])

    async with session_factory() as session:
        job = await JobRepository(session).get_job(job_id)

    assert job is not None
    assert job.seed_username == "testuser"
    assert job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_analyze_now_strips_at_prefix(client, session_factory):
    mock_thread = MagicMock()
    with (
        patch("api.routers.jobs.threading.Thread", return_value=mock_thread),
        patch("api.routers.jobs.run_crawl_in_thread"),
    ):
        resp = await client.post("/jobs/analyze-now", json={"username": "@somehandle"})

    assert resp.status_code == 202
    assert resp.json()["username"] == "somehandle"


@pytest.mark.asyncio
async def test_analyze_now_spawns_thread(client, session_factory):
    mock_thread = MagicMock()
    with (
        patch("api.routers.jobs.threading.Thread", return_value=mock_thread) as thread_cls,
        patch("api.routers.jobs.run_crawl_in_thread"),
    ):
        resp = await client.post("/jobs/analyze-now", json={"username": "spawntest"})

    assert resp.status_code == 202
    thread_cls.assert_called_once()
    call_kwargs = thread_cls.call_args
    assert call_kwargs.kwargs.get("target") is not None or call_kwargs.args
    mock_thread.start.assert_called_once()
