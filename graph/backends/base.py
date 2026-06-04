from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypedDict


class NodeData(TypedDict):
    node_id: str        # "platform:@handle"
    labels: list[str]   # e.g. ["Account"]
    props: dict[str, Any]


class EdgeData(TypedDict):
    src: str
    dst: str
    rel_type: str
    props: dict[str, Any]


class GraphData(TypedDict):
    nodes: list[NodeData]
    edges: list[EdgeData]


class AbstractGraphBackend(ABC):
    """Abstract base class for all graph storage backends.

    All methods are async to allow seamless drop-in of network-backed
    backends (e.g. Neo4j) without changing call-site signatures.
    NetworkX wraps sync operations directly in async def bodies.
    """

    @abstractmethod
    async def upsert_node(
        self,
        node_id: str,
        labels: list[str],
        props: dict[str, Any],
    ) -> None:
        """Insert or update a node.  Existing props are merged (not replaced)."""
        ...

    @abstractmethod
    async def upsert_edge(
        self,
        src: str,
        dst: str,
        rel_type: str,
        props: dict[str, Any],
    ) -> None:
        """Insert or update a directed edge.

        If an edge src→dst with the same rel_type already exists,
        update its props (and increment 'weight' if present) rather than
        creating a duplicate.
        """
        ...

    @abstractmethod
    async def get_neighbors(
        self,
        node_id: str,
        rel_types: list[str] | None = None,
        depth: int = 1,
    ) -> list[NodeData]:
        """Return all nodes reachable from node_id within *depth* hops.

        When rel_types is provided only edges with a matching rel_type
        are traversed.
        """
        ...

    @abstractmethod
    async def get_subgraph(
        self,
        node_id: str,
        depth: int,
        limit: int,
    ) -> GraphData:
        """Return a subgraph rooted at node_id.

        BFS up to *depth* hops; collect at most *limit* nodes total.
        All edges between collected nodes are included.
        """
        ...

    @abstractmethod
    async def run_cypher(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return rows as dicts.

        Raises NotImplementedError for backends that do not support Cypher.
        """
        ...

    @abstractmethod
    async def run_nx_query(self, fn: Callable[..., Any]) -> Any:
        """Pass the underlying networkx graph to *fn* and return its result.

        Raises NotImplementedError for non-networkx backends.
        Signature: fn(graph: nx.MultiDiGraph) -> Any
        """
        ...

    @abstractmethod
    async def node_count(self) -> int:
        """Return the total number of nodes in the graph."""
        ...

    @abstractmethod
    async def edge_count(self) -> int:
        """Return the total number of edges (including parallel edges)."""
        ...

    @abstractmethod
    async def save(self, path: str) -> None:
        """Persist the graph to *path*.

        Format is inferred from the file extension:
          .pkl  → Python pickle (fast, not portable)
          other → GraphML XML (portable, slower)
        Parent directories are created automatically.
        """
        ...

    @abstractmethod
    async def load(self, path: str) -> None:
        """Replace the current graph with data loaded from *path*.

        Format is inferred from the file extension (same rules as save).
        """
        ...
