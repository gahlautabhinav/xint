from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.extractors.twitter import TweetData
from storage.models.tweet import Tweet


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class TweetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(self, account_id: uuid.UUID, tweets: list[TweetData]) -> int:
        # Deduplicate within incoming batch — X sometimes renders same tweet twice
        _seen: dict[str, TweetData] = {}
        for tw in tweets:
            if tw.tweet_id and tw.tweet_id not in _seen:
                _seen[tw.tweet_id] = tw
        to_store = list(_seen.values())
        if not to_store:
            return 0
        existing_stmt = select(Tweet.tweet_id).where(
            Tweet.account_id == account_id,
            Tweet.tweet_id.in_([tw.tweet_id for tw in to_store]),
        )
        result = await self._session.execute(existing_stmt)
        existing_ids = {row[0] for row in result}

        now = datetime.now(timezone.utc)
        count = 0
        for tw in to_store:
            if tw.tweet_id in existing_ids:
                continue
            self._session.add(Tweet(
                account_id=account_id,
                tweet_id=tw.tweet_id,
                text=tw.text,
                timestamp=_parse_ts(tw.timestamp),
                reply_to=tw.reply_to,
                quote_url=tw.quote_url,
                retweeted_from=tw.retweeted_from,
                geo_location=tw.geo_location,
                mentions=tw.mentions or [],
                hashtags=tw.hashtags or [],
                media_urls=tw.media_urls or [],
                scraped_at=now,
            ))
            count += 1
        if count:
            await self._session.flush()
        return count

    async def get_tweets(
        self, account_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[Tweet], int]:
        count_stmt = (
            select(func.count())
            .select_from(Tweet)
            .where(Tweet.account_id == account_id)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(Tweet)
            .where(Tweet.account_id == account_id)
            .order_by(Tweet.timestamp.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total
