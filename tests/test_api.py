from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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
        # Patch Thread so no real browser/crawl thread spawns; we only verify
        # the endpoint persists a real job and hands it to the worker.
        with patch("api.routers.jobs.threading.Thread") as MockThread:
            r = await client.post(
                "/jobs",
                json={"seed_username": "elonmusk", "max_depth": 1, "max_accounts": 10},
            )

        assert r.status_code == 202
        data = r.json()
        assert data["seed_username"] == "elonmusk"
        assert data["status"] in ("RUNNING", "COMPLETED", "PENDING")
        MockThread.assert_called_once()
        MockThread.return_value.start.assert_called_once()

        # The returned id must be a real, persisted job (no synthetic placeholder).
        async with session_factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job(uuid.UUID(data["id"]))
        assert job is not None
        assert job.seed_username == "elonmusk"

    async def test_validation_max_depth(self, client: AsyncClient):
        r = await client.post(
            "/jobs",
            json={"seed_username": "x", "max_depth": 99},
        )
        assert r.status_code == 422

    async def test_validation_empty_username(self, client: AsyncClient):
        r = await client.post("/jobs", json={"seed_username": ""})
        assert r.status_code == 422


async def _make_job(session_factory, status: JobStatus) -> CrawlJob:
    async with session_factory() as session:
        job = await JobRepository(session).create_job(
            seed_username="runner",
            max_depth=1,
            max_accounts=10,
            status=status,
        )
        await session.commit()
        return job


# ---------------------------------------------------------------------------
# POST /jobs/{id}/cancel
# ---------------------------------------------------------------------------


class TestCancelJob:
    async def test_cancel_running(self, client: AsyncClient, session_factory):
        job = await _make_job(session_factory, JobStatus.RUNNING)
        r = await client.post(f"/jobs/{job.id}/cancel")
        assert r.status_code == 202
        assert r.json()["status"] == "CANCELLED"

        async with session_factory() as session:
            refreshed = await JobRepository(session).get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.CANCELLED

    async def test_cancel_terminal_conflict(self, client: AsyncClient, seed_job: CrawlJob):
        r = await client.post(f"/jobs/{seed_job.id}/cancel")
        assert r.status_code == 409

    async def test_cancel_not_found(self, client: AsyncClient):
        r = await client.post(f"/jobs/{uuid.uuid4()}/cancel")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /jobs/{id}
# ---------------------------------------------------------------------------


class TestDeleteJob:
    async def test_delete_terminal_removes_job_and_events(
        self, client: AsyncClient, seed_job: CrawlJob, session_factory
    ):
        async with session_factory() as session:
            repo = JobRepository(session)
            await repo.emit_event(seed_job.id, "account_scraped", {"username": "x"})
            await session.commit()

        r = await client.delete(f"/jobs/{seed_job.id}")
        assert r.status_code == 204

        async with session_factory() as session:
            repo = JobRepository(session)
            assert await repo.get_job(seed_job.id) is None
            assert await repo.get_events_since(seed_job.id, 0) == []

    async def test_delete_running_conflict(self, client: AsyncClient, session_factory):
        job = await _make_job(session_factory, JobStatus.RUNNING)
        r = await client.delete(f"/jobs/{job.id}")
        assert r.status_code == 409

    async def test_delete_not_found(self, client: AsyncClient):
        r = await client.delete(f"/jobs/{uuid.uuid4()}")
        assert r.status_code == 404


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
# GET /graph/hashtags
# ---------------------------------------------------------------------------


async def _seed_tagged(session_factory, username: str, tags: dict[str, int]) -> None:
    async with session_factory() as session:
        await AccountRepository(session).upsert(
            username=username,
            platform="twitter",
            raw_data={"hashtags": [{"tag": t, "count": c} for t, c in tags.items()]},
        )
        await session.commit()


class TestHashtagAnalysis:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/graph/hashtags")
        assert r.status_code == 200
        data = r.json()
        assert data["account_count"] == 0
        assert data["top_hashtags"] == []
        assert data["pairs"] == []

    async def test_ranking_and_pairs(self, client: AsyncClient, session_factory):
        await _seed_tagged(session_factory, "alice", {"btc": 5, "eth": 1})
        await _seed_tagged(session_factory, "bob", {"btc": 2, "doge": 4})

        r = await client.get("/graph/hashtags?min_shared=1")
        assert r.status_code == 200
        data = r.json()
        assert data["account_count"] == 2
        top = {h["tag"]: h["count"] for h in data["top_hashtags"]}
        assert top["btc"] == 7
        assert len(data["pairs"]) == 1
        pair = data["pairs"][0]
        assert {pair["source"], pair["target"]} == {"alice", "bob"}
        assert pair["shared"] == ["btc"]

    async def test_min_shared_filters(self, client: AsyncClient, session_factory):
        await _seed_tagged(session_factory, "alice", {"btc": 1, "eth": 1})
        await _seed_tagged(session_factory, "bob", {"btc": 1})

        r = await client.get("/graph/hashtags?min_shared=2")
        assert r.status_code == 200
        assert r.json()["pairs"] == []


# ---------------------------------------------------------------------------
# GET /geo/locations
# ---------------------------------------------------------------------------


async def _seed_located(
    session_factory,
    username: str,
    *,
    location: str | None = None,
    geo_locations: list[str] | None = None,
    utc_offset: int | None = None,
) -> None:
    raw: dict = {}
    if geo_locations is not None:
        raw["geo_locations"] = geo_locations
    if utc_offset is not None:
        raw["timezone"] = {"utc_offset": utc_offset}
    async with session_factory() as session:
        await AccountRepository(session).upsert(
            username=username,
            platform="twitter",
            location=location,
            raw_data=raw or None,
        )
        await session.commit()


def _fake_geocode(result):
    """Return an AsyncMock standing in for nominatim_geocode."""
    from scraper.analysis.geo import GeoResult  # noqa: F401

    async def _call(query, client=None):
        return result(query) if callable(result) else result

    return AsyncMock(side_effect=_call)


class TestGeoLocations:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/geo/locations")
        assert r.status_code == 200
        data = r.json()
        assert data["points"] == []
        assert data["timezone_only"] == []
        assert data["pending"] == 0
        assert data["total_accounts"] == 0

    async def test_geocodes_and_caches(self, client: AsyncClient, session_factory):
        from scraper.analysis.geo import GeoResult

        await _seed_located(session_factory, "alice", location="London")
        mock = _fake_geocode(GeoResult(lat=51.5, lon=-0.12, display_name="London, UK", importance=0.8))

        with (
            patch("api.routers.geo.nominatim_geocode", mock),
            patch("api.routers.geo.asyncio.sleep", new=AsyncMock()),
        ):
            r1 = await client.get("/geo/locations")
            assert r1.status_code == 200
            d1 = r1.json()
            assert len(d1["points"]) == 1
            p = d1["points"][0]
            assert p["username"] == "alice"
            assert p["lat"] == 51.5
            assert p["source"] == "profile"
            assert p["confidence"] == "high"
            assert d1["pending"] == 0
            assert d1["located"] == 1
            assert mock.call_count == 1

            # Second call hits the persistent cache — no new Nominatim request.
            r2 = await client.get("/geo/locations")
            assert len(r2.json()["points"]) == 1
            assert mock.call_count == 1

    async def test_tweet_geo_outranks_profile(self, client: AsyncClient, session_factory):
        from scraper.analysis.geo import GeoResult

        await _seed_located(
            session_factory, "bob", location="London", geo_locations=["Tokyo"]
        )
        mock = _fake_geocode(
            lambda q: GeoResult(lat=35.6, lon=139.7, display_name=q, importance=0.7)
        )
        with (
            patch("api.routers.geo.nominatim_geocode", mock),
            patch("api.routers.geo.asyncio.sleep", new=AsyncMock()),
        ):
            r = await client.get("/geo/locations")
        points = r.json()["points"]
        assert len(points) == 1
        assert points[0]["source"] == "tweet_geo"
        assert points[0]["confidence"] == "high"

    async def test_negative_cache_no_point(self, client: AsyncClient, session_factory):
        await _seed_located(session_factory, "carol", location="Atlantis")
        mock = _fake_geocode(None)  # Nominatim finds nothing
        with (
            patch("api.routers.geo.nominatim_geocode", mock),
            patch("api.routers.geo.asyncio.sleep", new=AsyncMock()),
        ):
            r1 = await client.get("/geo/locations")
            assert r1.json()["points"] == []
            assert mock.call_count == 1
            # Negative cached — not re-queried.
            await client.get("/geo/locations")
            assert mock.call_count == 1

    async def test_timezone_only(self, client: AsyncClient, session_factory):
        await _seed_located(session_factory, "dave", utc_offset=-5)
        r = await client.get("/geo/locations")
        data = r.json()
        assert data["points"] == []
        assert len(data["timezone_only"]) == 1
        tz = data["timezone_only"][0]
        assert tz["username"] == "dave"
        assert tz["timezone_utc_offset"] == -5
        assert tz["approx_longitude"] == -75.0

    async def test_max_new_budget_leaves_pending(self, client: AsyncClient, session_factory):
        from scraper.analysis.geo import GeoResult

        await _seed_located(session_factory, "a", location="London")
        await _seed_located(session_factory, "b", location="Paris")
        await _seed_located(session_factory, "c", location="Tokyo")
        mock = _fake_geocode(
            lambda q: GeoResult(lat=1.0, lon=2.0, display_name=q, importance=0.5)
        )
        with (
            patch("api.routers.geo.nominatim_geocode", mock),
            patch("api.routers.geo.asyncio.sleep", new=AsyncMock()),
        ):
            r = await client.get("/geo/locations?max_new=1")
        data = r.json()
        assert len(data["points"]) == 1
        assert data["pending"] == 2
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# POST /jobs/discover
# ---------------------------------------------------------------------------


async def _seed_stub(session_factory, username: str) -> None:
    """An edge-only stub: account row with no raw_data (never scraped)."""
    async with session_factory() as session:
        await AccountRepository(session).upsert(username=username, platform="twitter")
        await session.commit()


class TestDiscoverAll:
    async def test_queues_uncrawled_stubs(
        self, client: AsyncClient, graph_backend: NetworkxBackend, session_factory
    ):
        from graph.schema.nodes import make_node_id

        seed = make_node_id("twitter", "alice")
        await graph_backend.upsert_node(seed, ["Account"], {})
        for h in ("bob", "carol"):
            nid = make_node_id("twitter", h)
            await graph_backend.upsert_node(nid, ["Account"], {})
            await graph_backend.upsert_edge(seed, nid, "MENTIONS", {})
        # alice is crawled; bob/carol are stubs
        await _seed_located(session_factory, "alice", location="NYC")
        await _seed_stub(session_factory, "bob")
        await _seed_stub(session_factory, "carol")

        with patch("api.routers.jobs.threading.Thread") as MockThread:
            r = await client.post("/jobs/discover", json={"seed": "alice", "depth": 2})
        assert r.status_code == 202
        data = r.json()
        assert data["queued"] == 2  # bob + carol
        assert data["remaining"] == 0
        assert data["job_id"] is not None
        MockThread.assert_called_once()
        MockThread.return_value.start.assert_called_once()

    async def test_batch_cap_leaves_remaining(
        self, client: AsyncClient, graph_backend: NetworkxBackend, session_factory
    ):
        from graph.schema.nodes import make_node_id

        seed = make_node_id("twitter", "hub")
        await graph_backend.upsert_node(seed, ["Account"], {})
        for h in ("s1", "s2", "s3"):
            nid = make_node_id("twitter", h)
            await graph_backend.upsert_node(nid, ["Account"], {})
            await graph_backend.upsert_edge(seed, nid, "MENTIONS", {})
            await _seed_stub(session_factory, h)
        await _seed_located(session_factory, "hub", location="NYC")

        with patch("api.routers.jobs.threading.Thread"):
            r = await client.post(
                "/jobs/discover", json={"seed": "hub", "depth": 2, "max_accounts": 2}
            )
        data = r.json()
        assert data["queued"] == 2
        assert data["remaining"] == 1

    async def test_nothing_to_discover(
        self, client: AsyncClient, graph_backend: NetworkxBackend, session_factory
    ):
        from graph.schema.nodes import make_node_id

        seed = make_node_id("twitter", "solo")
        await graph_backend.upsert_node(seed, ["Account"], {})
        await _seed_located(session_factory, "solo", location="NYC")

        with patch("api.routers.jobs.threading.Thread") as MockThread:
            r = await client.post("/jobs/discover", json={"seed": "solo", "depth": 2})
        assert r.status_code == 202
        data = r.json()
        assert data["queued"] == 0
        assert data["job_id"] is None
        MockThread.assert_not_called()

    async def test_seed_not_in_graph_404(self, client: AsyncClient):
        r = await client.post("/jobs/discover", json={"seed": "ghost", "depth": 2})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /geo/locations?seed=  (seed-scoped map)
# ---------------------------------------------------------------------------


class TestGeoSeedScope:
    async def test_seed_scopes_to_subgraph(
        self, client: AsyncClient, graph_backend: NetworkxBackend, session_factory
    ):
        from graph.schema.nodes import make_node_id
        from scraper.analysis.geo import GeoResult

        # graph: alice -> bob ; eve is unrelated
        a = make_node_id("twitter", "alice")
        b = make_node_id("twitter", "bob")
        await graph_backend.upsert_node(a, ["Account"], {})
        await graph_backend.upsert_node(b, ["Account"], {})
        await graph_backend.upsert_edge(a, b, "MENTIONS", {})
        await _seed_located(session_factory, "alice", location="London")
        await _seed_located(session_factory, "bob", location="Paris")
        await _seed_located(session_factory, "eve", location="Tokyo")  # not in alice's graph

        mock = _fake_geocode(
            lambda q: GeoResult(lat=1.0, lon=2.0, display_name=q, importance=0.6)
        )
        with (
            patch("api.routers.geo.nominatim_geocode", mock),
            patch("api.routers.geo.asyncio.sleep", new=AsyncMock()),
        ):
            r = await client.get("/geo/locations?seed=alice&depth=2")
        usernames = {p["username"] for p in r.json()["points"]}
        assert usernames == {"alice", "bob"}
        assert "eve" not in usernames


# ---------------------------------------------------------------------------
# GET /enrich/username
# ---------------------------------------------------------------------------


class TestUsernameEnum:
    async def test_returns_results(self, client: AsyncClient):
        from scraper.enrich.username_enum import SiteResult

        fake = AsyncMock(
            return_value=[
                SiteResult("GitHub", "code", "https://github.com/alice", "found"),
                SiteResult("GitLab", "code", "https://gitlab.com/alice", "not_found"),
                SiteResult("Reddit", "social", "https://reddit.com/user/alice", "unknown"),
            ]
        )
        with patch("api.routers.enrich.enumerate_username", fake):
            r = await client.get("/enrich/username?username=alice")
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "alice"
        assert data["checked"] == 3
        assert data["found"] == 1
        assert {x["name"] for x in data["results"]} == {"GitHub", "GitLab", "Reddit"}

    async def test_strips_at_prefix(self, client: AsyncClient):
        from scraper.enrich.username_enum import SiteResult

        fake = AsyncMock(return_value=[SiteResult("GitHub", "code", "x", "found")])
        with patch("api.routers.enrich.enumerate_username", fake) as mock:
            r = await client.get("/enrich/username?username=@alice")
        assert r.status_code == 200
        assert r.json()["username"] == "alice"
        mock.assert_awaited_once_with("alice")

    async def test_rejects_invalid_username(self, client: AsyncClient):
        # Slash would let the handle inject a path into outbound URLs.
        r = await client.get("/enrich/username?username=foo%2Fbar")
        assert r.status_code == 400

    async def test_rejects_empty(self, client: AsyncClient):
        r = await client.get("/enrich/username?username=")
        assert r.status_code == 422  # fails Query min_length


# ---------------------------------------------------------------------------
# GET /enrich/pivots/{platform}/{handle}
# ---------------------------------------------------------------------------


class TestPivots:
    async def test_returns_grouped_links(self, client: AsyncClient, session_factory):
        async with session_factory() as session:
            await AccountRepository(session).upsert(
                username="alice",
                platform="twitter",
                display_name="Alice",
                website="alice.dev",
                profile_image_url="https://pbs.twimg.com/profile_images/1/a_normal.jpg",
                raw_data={"emails": ["alice@example.com"]},
            )
            await session.commit()

        r = await client.get("/enrich/pivots/twitter/alice")
        assert r.status_code == 200
        data = r.json()
        assert data["handle"] == "alice"
        groups = {link["group"] for link in data["links"]}
        assert {"reverse_image", "identity", "dork", "breach"} <= groups
        assert any("_400x400" in link["url"] for link in data["links"])

    async def test_strips_at(self, client: AsyncClient, seed_account: Account):
        r = await client.get("/enrich/pivots/twitter/@alice")
        assert r.status_code == 200
        assert r.json()["handle"] == "alice"

    async def test_not_found(self, client: AsyncClient):
        r = await client.get("/enrich/pivots/twitter/nobody")
        assert r.status_code == 404

    async def test_invalid_handle(self, client: AsyncClient):
        # '!' stays in one path segment but fails the strict handle charset.
        r = await client.get("/enrich/pivots/twitter/foo!bar")
        assert r.status_code == 400


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
