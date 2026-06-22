from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, DbSession
from api.schemas.accounts import AccountListResponse, AccountResponse
from api.schemas.tweets import TweetListResponse, TweetResponse
from storage.repositories.account_repo import AccountRepository
from storage.repositories.tweet_repo import TweetRepository

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    _key: ApiKeyCheck,
    session: DbSession,
    q: str | None = Query(default=None, description="Substring search across username/bio"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AccountListResponse:
    repo = AccountRepository(session)
    if q:
        accounts = await repo.search(q, limit=limit)
    else:
        from sqlalchemy import select

        from storage.models.account import Account

        stmt = (
            select(Account)
            .order_by(Account.scraped_at.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())

    total = await repo.count()
    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=total,
    )


@router.get("/{platform}/{handle}", response_model=AccountResponse)
async def get_account(
    platform: str,
    handle: str,
    _key: ApiKeyCheck,
    session: DbSession,
) -> AccountResponse:
    repo = AccountRepository(session)
    account = await repo.get_by_username(handle, platform=platform)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {platform}/{handle} not found",
        )
    return AccountResponse.model_validate(account)


@router.get("/{platform}/{handle}/tweets", response_model=TweetListResponse)
async def get_account_tweets(
    platform: str,
    handle: str,
    _key: ApiKeyCheck,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TweetListResponse:
    account_repo = AccountRepository(session)
    account = await account_repo.get_by_username(handle, platform=platform)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {platform}/{handle} not found",
        )
    tweet_repo = TweetRepository(session)
    tweets, total = await tweet_repo.get_tweets(account.id, limit=limit, offset=offset)
    items = [
        TweetResponse(
            id=tw.id,
            tweet_id=tw.tweet_id,
            text=tw.text,
            timestamp=tw.timestamp,
            reply_to=tw.reply_to,
            quote_url=tw.quote_url,
            retweeted_from=tw.retweeted_from,
            geo_location=tw.geo_location,
            mentions=tw.mentions or [],
            hashtags=tw.hashtags or [],
            scraped_at=tw.scraped_at,
            tweet_url=(
                f"https://x.com/{handle}/status/{tw.tweet_id}"
                if tw.tweet_id else None
            ),
        )
        for tw in tweets
    ]
    return TweetListResponse(items=items, total=total)
