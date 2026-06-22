from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from scraper.extractors.twitter import TweetData
from storage.base import Base
from storage.models import Account
from storage.repositories.account_repo import AccountRepository
from storage.repositories.tweet_repo import TweetRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def account(session: AsyncSession) -> Account:
    repo = AccountRepository(session)
    acc = await repo.upsert(username="testuser", platform="twitter")
    await session.commit()
    return acc


def make_tweet(tweet_id: str, text: str = "hello world") -> TweetData:
    return TweetData(
        tweet_id=tweet_id,
        text=text,
        timestamp="2024-01-15T10:30:00Z",
        mentions=["alice"],
        hashtags=["osint"],
        reply_to=None,
        quote_url=None,
        retweeted_from=None,
        geo_location=None,
    )


@pytest.mark.asyncio
async def test_bulk_upsert_stores_tweets(session, account):
    repo = TweetRepository(session)
    tweets = [make_tweet("111"), make_tweet("222")]
    count = await repo.bulk_upsert(account.id, tweets)
    assert count == 2
    stored, total = await repo.get_tweets(account.id)
    assert total == 2
    assert {t.tweet_id for t in stored} == {"111", "222"}


@pytest.mark.asyncio
async def test_bulk_upsert_deduplicates(session, account):
    repo = TweetRepository(session)
    await repo.bulk_upsert(account.id, [make_tweet("111")])
    await session.commit()
    count = await repo.bulk_upsert(account.id, [make_tweet("111"), make_tweet("222")])
    assert count == 1


@pytest.mark.asyncio
async def test_bulk_upsert_skips_tweets_without_id(session, account):
    repo = TweetRepository(session)
    no_id = TweetData(tweet_id=None, text="no id tweet", timestamp=None)
    count = await repo.bulk_upsert(account.id, [no_id])
    assert count == 0


@pytest.mark.asyncio
async def test_get_tweets_pagination(session, account):
    repo = TweetRepository(session)
    tweets = [make_tweet(str(i), f"tweet {i}") for i in range(10)]
    await repo.bulk_upsert(account.id, tweets)
    page, total = await repo.get_tweets(account.id, limit=3, offset=0)
    assert len(page) == 3
    assert total == 10


@pytest.mark.asyncio
async def test_get_tweets_empty(session, account):
    repo = TweetRepository(session)
    tweets, total = await repo.get_tweets(account.id)
    assert tweets == []
    assert total == 0
