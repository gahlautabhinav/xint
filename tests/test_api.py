from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import storage.models  # noqa: F401 — registers all models with Base
from api.main import create_app
from graph.backends.networkx_backend import NetworkxBackend
from storage.base import Base
from storage.models.account import Account
from storage.models.job import CrawlJob, JobStatus
from storage.repositories.account_repo import AccountRepository
from storage.repositories.job_repo import JobRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """FastAPI app with pre-populated app.state (bypasses lifespan)."""
    application = create_app()
    application.state.session_factory = session_factory
    application.state.graph = graph_backend
    application.state.api_key = None
    return application


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def seed_job(session_factory) -> CrawlJob:
    async with session_factory() as session:
        repo = JobRepository(session)
        job = await repo.create_job(
            seed_username="testuser",
            max_depth=2,
            max_accounts=50,
            status=JobStatus.COMPLETED,
            accounts_scraped=3,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        await session.commit()
        return job


@pytest.fixture
async def seed_account(session_factory) -> Account:
    async with session_factory() as session:
        repo = AccountRepository(session)
        acc = await repo.upsert(
            username="alice",
            platform="twitter",
            display_name="Alice",
            bio="test bio",
            followers_count=100,
            following_count=50,
            is_verified=False,
        )
        await session.commit()
        return acc


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_health_ok(self, client: AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/jobs")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_job(self, client: AsyncClient, seed_job: CrawlJob):
        r = await client.get("/jobs")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["seed_username"] == "testuser"
        assert items[0]["status"] == "COMPLETED"

    async def test_pagination(self, client: AsyncClient, session_factory):
        async with session_factory() as session:
            repo = JobRepository(session)
            for i in range(5):
                await repo.create_job(
                    seed_username=f"user{i}",
                    max_depth=1,
                    max_accounts=10,
                    status=JobStatus.COMPLETED,
                )
            await session.commit()

        r = await client.get("/jobs?limit=2&offset=0")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# GET /jobs/{id}
# ---------------------------------------------------------------------------


class TestGetJob:
    async def test_found(self, client: AsyncClient, seed_job: CrawlJob):
        r = await client.get(f"/jobs/{seed_job.id}")
        assert r.status_code == 200
        assert r.json()["id"] == str(seed_job.id)

    async def test_not_found(self, client: AsyncClient):
        r = await client.get(f"/jobs/{uuid.uuid4()}")
        assert r.status_code == 404

    async def test_invalid_uuid(self, client: AsyncClient):
        r = await client.get("/jobs/not-a-uuid")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /jobs/{id}/events
# ---------------------------------------------------------------------------


class TestGetJobEvents:
    async def test_empty_events(self, client: AsyncClient, seed_job: CrawlJob):
        r = await client.get(f"/jobs/{seed_job.id}/events")
        assert r.status_code == 200
        data = r.json()
        assert data["events"] == []
        assert data["last_sequence"] == 0

    async def test_events_returned(self, client: AsyncClient, seed_job: CrawlJob, session_factory):
        async with session_factory() as session:
            repo = JobRepository(session)
            await repo.emit_event(seed_job.id, "account_scraped", {"username": "alice"})
            await repo.emit_event(seed_job.id, "account_scraped", {"username": "bob"})
            await session.commit()

        r = await client.get(f"/jobs/{seed_job.id}/events")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 2
        assert events[0]["event_type"] == "account_scraped"
        assert r.json()["last_sequence"] == 2

    async def test_since_filter(self, client: AsyncClient, seed_job: CrawlJob, session_factory):
        async with session_factory() as session:
            repo = JobRepository(session)
            await repo.emit_event(seed_job.id, "e1", {})
            await repo.emit_event(seed_job.id, "e2", {})
            await repo.emit_event(seed_job.id, "e3", {})
            await session.commit()

        r = await client.get(f"/jobs/{seed_job.id}/events?since=1")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 2
        assert events[0]["event_type"] == "e2"

    async def test_job_not_found(self, client: AsyncClient):
        r = await client.get(f"/jobs/{uuid.uuid4()}/events")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /jobs
# ---------------------------------------------------------------------------


class TestCreateJob:
    async def test_creates_job(self, client: AsyncClient, session_factory):
        with patch("api.routers.jobs.AccountCrawler") as MockCrawler:
            mock_instance = MagicMock()
            mock_run = AsyncMock(return_value=uuid.uuid4())
            mock_instance.run = mock_run
            MockCrawler.return_value = mock_instance

            r = await client.post(
                "/jobs",
                json={"seed_username": "elonmusk", "max_depth": 1, "max_accounts": 10},
            )

        assert r.status_code == 202
        data = r.json()
        assert data["seed_username"] == "elonmusk"
        assert data["status"] in ("RUNNING", "COMPLETED", "PENDING")

    async def test_validation_max_depth(self, client: AsyncClient):
        r = await client.post(
            "/jobs",
            json={"seed_username": "x", "max_depth": 99},
        )
        assert r.status_code == 422

    async def test_validation_empty_username(self, client: AsyncClient):
        r = await client.post("/jobs", json={"seed_username": ""})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /accounts
# ---------------------------------------------------------------------------


class TestListAccounts:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/accounts")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_account(self, client: AsyncClient, seed_account: Account):
        r = await client.get("/accounts")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["username"] == "alice"

    async def test_search(self, client: AsyncClient, seed_account: Account):
        r = await client.get("/accounts?q=alice")
        assert r.status_code == 200
        assert r.json()["items"][0]["username"] == "alice"

    async def test_search_no_match(self, client: AsyncClient, seed_account: Account):
        r = await client.get("/accounts?q=zzznomatch")
        assert r.status_code == 200
        assert r.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /accounts/{platform}/{handle}
# ---------------------------------------------------------------------------


class TestGetAccount:
    async def test_found(self, client: AsyncClient, seed_account: Account):
        r = await client.get("/accounts/twitter/alice")
        assert r.status_code == 200
        assert r.json()["username"] == "alice"
        assert r.json()["platform"] == "twitter"

    async def test_not_found(self, client: AsyncClient):
        r = await client.get("/accounts/twitter/nobody")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /graph/{handle}/subgraph
# ---------------------------------------------------------------------------


class TestGetSubgraph:
    async def test_empty_graph_404(self, client: AsyncClient):
        r = await client.get("/graph/nobody/subgraph")
        assert r.status_code == 404

    async def test_returns_subgraph(self, client: AsyncClient, graph_backend: NetworkxBackend):
        from graph.schema.nodes import make_node_id

        nid = make_node_id("twitter", "graphuser")
        await graph_backend.upsert_node(nid, ["Account"], {"display_name": "Graph User"})
        await graph_backend.upsert_node(make_node_id("twitter", "friend"), ["Account"], {})
        await graph_backend.upsert_edge(nid, make_node_id("twitter", "friend"), "MENTIONS", {})

        r = await client.get("/graph/graphuser/subgraph?depth=1")
        assert r.status_code == 200
        data = r.json()
        assert len(data["nodes"]) >= 1
        assert any(n["node_id"] == nid for n in data["nodes"])

    async def test_depth_validation(self, client: AsyncClient):
        r = await client.get("/graph/x/subgraph?depth=99")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /graph/{handle}/neighbors
# ---------------------------------------------------------------------------


class TestGetNeighbors:
    async def test_no_neighbors(self, client: AsyncClient, graph_backend: NetworkxBackend):
        from graph.schema.nodes import make_node_id

        nid = make_node_id("twitter", "loner")
        await graph_backend.upsert_node(nid, ["Account"], {})

        r = await client.get("/graph/loner/neighbors")
        assert r.status_code == 200
        data = r.json()
        assert data["node_id"] == nid
        assert data["neighbors"] == []

    async def test_returns_neighbors(self, client: AsyncClient, graph_backend: NetworkxBackend):
        from graph.schema.nodes import make_node_id

        src = make_node_id("twitter", "hub")
        dst1 = make_node_id("twitter", "spoke1")
        dst2 = make_node_id("twitter", "spoke2")
        await graph_backend.upsert_node(src, ["Account"], {})
        await graph_backend.upsert_node(dst1, ["Account"], {})
        await graph_backend.upsert_node(dst2, ["Account"], {})
        await graph_backend.upsert_edge(src, dst1, "MENTIONS", {})
        await graph_backend.upsert_edge(src, dst2, "REPLIES_TO", {})

        r = await client.get("/graph/hub/neighbors")
        assert r.status_code == 200
        neighbor_ids = {n["node_id"] for n in r.json()["neighbors"]}
        assert dst1 in neighbor_ids
        assert dst2 in neighbor_ids


# ---------------------------------------------------------------------------
# API key enforcement
# ---------------------------------------------------------------------------


class TestApiKey:
    async def test_no_key_configured_passes(self, client: AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200

    async def test_key_required_rejected(self, app, session_factory):
        app.state.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/jobs")
            assert r.status_code == 401

    async def test_key_required_accepted(self, app, session_factory):
        app.state.api_key = "secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/jobs", headers={"X-API-Key": "secret"})
            assert r.status_code == 200
