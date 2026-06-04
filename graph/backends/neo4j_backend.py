from __future__ import annotations

from collections.abc import Callable
from typing import Any

from graph.backends.base import AbstractGraphBackend, GraphData, NodeData

_NOT_IMPLEMENTED_MSG = (
    "Neo4j backend not yet implemented. "
    "Use NetworkxBackend for local development, or implement this class "
    "using the neo4j Python driver (pip install neo4j) for production."
)


class Neo4jBackend(AbstractGraphBackend):
    """Stub Neo4j backend — all operations raise :class:`NotImplementedError`.

    This class holds the correct constructor signature and satisfies the
    :class:`AbstractGraphBackend` interface so type-checkers pass.
    Full implementation is deferred to Phase 3.

    Parameters
    ----------
    url:
        Bolt or neo4j+s URI, e.g. ``"bolt://localhost:7687"``.
    user:
        Neo4j username (default ``"neo4j"``).
    password:
        Neo4j password.
    """

    def __init__(self, url: str, user: str, password: str) -> None:
        self._url = url
        self._user = user
        self._password = password

    # ------------------------------------------------------------------
    # AbstractGraphBackend — all raise NotImplementedError
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        node_id: str,
        labels: list[str],
        props: dict[str, Any],
    ) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def upsert_edge(
        self,
        src: str,
        dst: str,
        rel_type: str,
        props: dict[str, Any],
    ) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def get_neighbors(
        self,
        node_id: str,
        rel_types: list[str] | None = None,
        depth: int = 1,
    ) -> list[NodeData]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def get_subgraph(
        self,
        node_id: str,
        depth: int,
        limit: int,
    ) -> GraphData:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def run_cypher(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def run_nx_query(self, fn: Callable[..., Any]) -> Any:
        raise NotImplementedError(
            "Neo4j backend does not support networkx queries. "
            "Use run_cypher() instead (not yet implemented)."
        )

    async def node_count(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def edge_count(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def save(self, path: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def load(self, path: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
