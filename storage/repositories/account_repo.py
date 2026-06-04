from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.account import Account


class AccountRepository:
    """Data-access layer for :class:`~storage.models.account.Account` records.

    Uses a select-then-insert/update pattern for cross-database compatibility
    (works identically on SQLite and PostgreSQL without dialect-specific SQL).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert(self, **kwargs: Any) -> Account:
        """Insert a new account or update it if (platform, username) already exists.

        Keyword arguments map directly to :class:`Account` columns.
        Returns the persisted :class:`Account` instance.
        """
        platform: str = kwargs.get("platform", "twitter")
        username: str = kwargs["username"]

        existing = await self.get_by_username(username, platform)
        if existing is not None:
            # Update mutable fields, skip PK / identity fields
            skip = {"id", "username", "platform"}
            for key, value in kwargs.items():
                if key not in skip:
                    setattr(existing, key, value)
            existing.scraped_at = kwargs.get("scraped_at", datetime.now(timezone.utc))
            await self._session.flush()
            return existing

        account = Account(**kwargs)
        self._session.add(account)
        await self._session.flush()
        return account

    async def bulk_upsert(self, accounts: list[dict[str, Any]]) -> int:
        """Upsert a list of account dicts; returns the number processed."""
        count = 0
        for record in accounts:
            await self.upsert(**record)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_username(
        self,
        username: str,
        platform: str = "twitter",
    ) -> Account | None:
        """Return an account by (platform, username), or ``None`` if not found."""
        stmt = select(Account).where(
            Account.platform == platform,
            Account.username == username,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        """Return an account by primary key, or ``None`` if not found."""
        stmt = select(Account).where(Account.id == account_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_depth(self, max_depth: int) -> list[Account]:
        """Return all accounts whose ``scrape_depth`` is <= *max_depth*."""
        stmt = (
            select(Account)
            .where(Account.scrape_depth <= max_depth)
            .order_by(Account.scrape_depth)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search(self, query: str, limit: int = 50) -> list[Account]:
        """Full-text substring search across username, display_name, and bio.

        Uses ``LIKE`` with ``%query%`` for broad cross-db compatibility.
        On Postgres this becomes a case-insensitive ``ILIKE`` via the
        ``ilike`` method; on SQLite ``LIKE`` is case-insensitive for ASCII
        by default.
        """
        pattern = f"%{query}%"
        stmt = (
            select(Account)
            .where(
                or_(
                    Account.username.ilike(pattern),
                    Account.display_name.ilike(pattern),
                    Account.bio.ilike(pattern),
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Return the total number of accounts in the database."""
        stmt = select(func.count()).select_from(Account)
        result = await self._session.execute(stmt)
        return result.scalar_one()
