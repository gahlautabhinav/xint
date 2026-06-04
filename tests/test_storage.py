from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import storage.models  # noqa: F401 — registers all models
from storage.base import Base
from storage.models.account import Account
from storage.models.job import JobStatus
from storage.models.relationship import RelType
from storage.repositories.account_repo import AccountRepository
from storage.repositories.job_repo import JobRepository
from storage.repositories.relationship_repo import RelationshipRepository

# ---------------------------------------------------------------------------
# Shared in-memory SQLite fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def session() -> AsyncSession:  # type: ignore[return]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


# ---------------------------------------------------------------------------
# AccountRepository
# ---------------------------------------------------------------------------

class TestAccountRepository:
    async def test_upsert_insert(self, session: AsyncSession):
        repo = AccountRepository(session)
        acc = await repo.upsert(username="alice", platform="twitter")
        await session.commit()
        assert acc.id is not None
        assert acc.username == "alice"

    async def test_upsert_update(self, session: AsyncSession):
        repo = AccountRepository(session)
        await repo.upsert(username="bob", platform="twitter", followers_count=10)
        await session.commit()
        updated = await repo.upsert(username="bob", platform="twitter", followers_count=999)
        await session.commit()
        assert updated.followers_count == 999

    async def test_upsert_idempotent_identity(self, session: AsyncSession):
        repo = AccountRepository(session)
        a1 = await repo.upsert(username="carol", platform="twitter")
        a2 = await repo.upsert(username="carol", platform="twitter")
        await session.commit()
        assert a1.id == a2.id

    async def test_bulk_upsert_count(self, session: AsyncSession):
        repo = AccountRepository(session)
        records = [{"username": f"user{i}", "platform": "twitter"} for i in range(5)]
        count = await repo.bulk_upsert(records)
        await session.commit()
        assert count == 5
        assert await repo.count() == 5

    async def test_get_by_username(self, session: AsyncSession):
        repo = AccountRepository(session)
        await repo.upsert(username="dave", platform="twitter")
        await session.commit()
        found = await repo.get_by_username("dave")
        assert found is not None
        assert found.username == "dave"

    async def test_get_by_username_missing(self, session: AsyncSession):
        repo = AccountRepository(session)
        assert await repo.get_by_username("nobody") is None

    async def test_get_by_depth(self, session: AsyncSession):
        repo = AccountRepository(session)
        await repo.upsert(username="depth0", scrape_depth=0)
        await repo.upsert(username="depth1", scrape_depth=1)
        await repo.upsert(username="depth2", scrape_depth=2)
        await session.commit()
        results = await repo.get_by_depth(1)
        usernames = {a.username for a in results}
        assert "depth0" in usernames
        assert "depth1" in usernames
        assert "depth2" not in usernames

    async def test_search(self, session: AsyncSession):
        repo = AccountRepository(session)
        await repo.upsert(username="searchme", display_name="Search Target")
        await repo.upsert(username="other", display_name="Unrelated")
        await session.commit()
        results = await repo.search("search")
        usernames = [a.username for a in results]
        assert "searchme" in usernames
        assert "other" not in usernames

    async def test_count(self, session: AsyncSession):
        repo = AccountRepository(session)
        assert await repo.count() == 0
        await repo.upsert(username="one")
        await repo.upsert(username="two")
        await session.commit()
        assert await repo.count() == 2


# ---------------------------------------------------------------------------
# RelationshipRepository
# ---------------------------------------------------------------------------

class TestRelationshipRepository:
    async def _make_accounts(self, session: AsyncSession) -> tuple[Account, Account]:
        repo = AccountRepository(session)
        src = await repo.upsert(username="src_user")
        dst = await repo.upsert(username="dst_user")
        await session.commit()
        return src, dst

    async def test_upsert_creates(self, session: AsyncSession):
        src, dst = await self._make_accounts(session)
        rel_repo = RelationshipRepository(session)
        rel = await rel_repo.upsert(src.id, dst.id, RelType.FOLLOWS)
        await session.commit()
        assert rel.source_account_id == src.id
        assert rel.rel_type == RelType.FOLLOWS

    async def test_upsert_increments_evidence(self, session: AsyncSession):
        src, dst = await self._make_accounts(session)
        rel_repo = RelationshipRepository(session)
        await rel_repo.upsert(src.id, dst.id, RelType.MENTIONS)
        await rel_repo.upsert(src.id, dst.id, RelType.MENTIONS)
        rel = await rel_repo.upsert(src.id, dst.id, RelType.MENTIONS)
        await session.commit()
        assert rel.evidence_count == 3

    async def test_upsert_different_rel_types_are_separate(self, session: AsyncSession):
        src, dst = await self._make_accounts(session)
        rel_repo = RelationshipRepository(session)
        await rel_repo.upsert(src.id, dst.id, RelType.FOLLOWS)
        await rel_repo.upsert(src.id, dst.id, RelType.MENTIONS)
        await session.commit()
        assert await rel_repo.count() == 2

    async def test_get_by_account_outgoing(self, session: AsyncSession):
        src, dst = await self._make_accounts(session)
        rel_repo = RelationshipRepository(session)
        await rel_repo.upsert(src.id, dst.id, RelType.REPLIES_TO)
        await session.commit()
        rels = await rel_repo.get_by_account(src.id, direction="outgoing")
        assert len(rels) == 1
        assert rels[0].source_account_id == src.id

    async def test_get_by_account_incoming(self, session: AsyncSession):
        src, dst = await self._make_accounts(session)
        rel_repo = RelationshipRepository(session)
        await rel_repo.upsert(src.id, dst.id, RelType.FOLLOWS)
        await session.commit()
        rels = await rel_repo.get_by_account(dst.id, direction="incoming")
        assert len(rels) == 1
        assert rels[0].target_account_id == dst.id


# ---------------------------------------------------------------------------
# JobRepository
# ---------------------------------------------------------------------------

class TestJobRepository:
    async def test_create_and_get(self, session: AsyncSession):
        repo = JobRepository(session)
        job = await repo.create_job(seed_username="elonmusk", max_depth=2)
        await session.commit()
        fetched = await repo.get_job(job.id)
        assert fetched is not None
        assert fetched.seed_username == "elonmusk"
        assert fetched.status == JobStatus.PENDING

    async def test_update_job(self, session: AsyncSession):
        repo = JobRepository(session)
        job = await repo.create_job(seed_username="testuser")
        await session.commit()
        updated = await repo.update_job(job.id, status=JobStatus.RUNNING, accounts_scraped=5)
        await session.commit()
        assert updated is not None
        assert updated.status == JobStatus.RUNNING
        assert updated.accounts_scraped == 5

    async def test_list_jobs(self, session: AsyncSession):
        repo = JobRepository(session)
        await repo.create_job(seed_username="user1")
        await repo.create_job(seed_username="user2")
        await session.commit()
        jobs = await repo.list_jobs()
        assert len(jobs) == 2

    async def test_emit_event_sequence(self, session: AsyncSession):
        repo = JobRepository(session)
        job = await repo.create_job(seed_username="eventtest")
        await session.commit()
        e1 = await repo.emit_event(job.id, "started", {"msg": "go"})
        e2 = await repo.emit_event(job.id, "progress", {"count": 1})
        e3 = await repo.emit_event(job.id, "completed")
        await session.commit()
        assert e1.sequence == 1
        assert e2.sequence == 2
        assert e3.sequence == 3

    async def test_get_events_since(self, session: AsyncSession):
        repo = JobRepository(session)
        job = await repo.create_job(seed_username="ssetest")
        await session.commit()
        for i in range(5):
            await repo.emit_event(job.id, "tick", {"i": i})
        await session.commit()
        events = await repo.get_events_since(job.id, since_sequence=2)
        assert len(events) == 3
        assert events[0].sequence == 3

    async def test_get_events_since_zero(self, session: AsyncSession):
        repo = JobRepository(session)
        job = await repo.create_job(seed_username="fulltest")
        await session.commit()
        await repo.emit_event(job.id, "a")
        await repo.emit_event(job.id, "b")
        await session.commit()
        events = await repo.get_events_since(job.id, since_sequence=0)
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Alembic round-trip (temp file DB)
# ---------------------------------------------------------------------------

async def test_alembic_upgrade_downgrade(tmp_path):
    """Verify alembic upgrade head → downgrade base against a real file DB."""

    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    assert db_path.exists()

    command.downgrade(cfg, "base")
    # DB file still exists after downgrade (empty schema)
    assert db_path.exists()

    command.upgrade(cfg, "head")  # re-apply cleanly
