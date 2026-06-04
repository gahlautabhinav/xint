from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.relationship import Relationship, RelType


class RelationshipRepository:
    """Data-access layer for :class:`~storage.models.relationship.Relationship` records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        rel_type: RelType,
        **kwargs: Any,
    ) -> Relationship:
        """Insert or update a relationship by its unique (source, target, rel_type) key.

        If the relationship already exists:
        - ``evidence_count`` is incremented by 1.
        - ``last_seen_at`` is updated to now.
        - Any additional *kwargs* fields are applied.

        If it does not exist, a new :class:`Relationship` is created with
        ``first_seen_at`` and ``last_seen_at`` both set to now.
        """
        existing = await self._get_unique(source_id, target_id, rel_type)
        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.evidence_count = (existing.evidence_count or 0) + 1
            existing.last_seen_at = now
            skip = {"id", "source_account_id", "target_account_id", "rel_type", "evidence_count", "last_seen_at"}
            for key, value in kwargs.items():
                if key not in skip:
                    setattr(existing, key, value)
            await self._session.flush()
            return existing

        rel = Relationship(
            source_account_id=source_id,
            target_account_id=target_id,
            rel_type=rel_type,
            first_seen_at=kwargs.pop("first_seen_at", now),
            last_seen_at=kwargs.pop("last_seen_at", now),
            **kwargs,
        )
        self._session.add(rel)
        await self._session.flush()
        return rel

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_account(
        self,
        account_id: uuid.UUID,
        direction: str = "both",
    ) -> list[Relationship]:
        """Return relationships involving *account_id*.

        Args:
            account_id: The account whose relationships to fetch.
            direction:  ``"outgoing"`` — only edges *from* this account;
                        ``"incoming"`` — only edges *to* this account;
                        ``"both"``     — all edges in either direction.
        """
        if direction == "outgoing":
            stmt = select(Relationship).where(
                Relationship.source_account_id == account_id
            )
        elif direction == "incoming":
            stmt = select(Relationship).where(
                Relationship.target_account_id == account_id
            )
        else:
            stmt = select(Relationship).where(
                or_(
                    Relationship.source_account_id == account_id,
                    Relationship.target_account_id == account_id,
                )
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Return the total number of relationships in the database."""
        stmt = select(func.count()).select_from(Relationship)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_unique(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        rel_type: RelType,
    ) -> Relationship | None:
        stmt = select(Relationship).where(
            Relationship.source_account_id == source_id,
            Relationship.target_account_id == target_id,
            Relationship.rel_type == rel_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
