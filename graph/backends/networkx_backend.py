from __future__ import annotations

import copy
import json
import pickle
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import networkx as nx

from graph.backends.base import (
    AbstractGraphBackend,
    EdgeData,
    GraphData,
    NodeData,
)


class NetworkxBackend(AbstractGraphBackend):
    """In-process graph backend backed by :class:`networkx.MultiDiGraph`.

    All public methods are declared ``async`` so the interface is identical to
    network-backed backends (e.g. Neo4j) and call-sites need not change.
    Because networkx is entirely synchronous and in-memory the implementations
    run the operations directly inside the coroutine body — no thread-pool
    offloading is needed for Phase 2.

    Node storage
    ------------
    Each node carries:
    - ``_labels`` (``list[str]``) — node type labels, e.g. ``["Account"]``
    - all user-supplied ``props`` flattened into the node attr dict

    Edge storage
    ------------
    Each edge carries:
    - ``rel_type`` (``str``) — relationship type constant from schema/edges.py
    - ``props``  (``dict[str, Any]``) — arbitrary metadata (weight, timestamp …)

    Deduplication
    -------------
    ``upsert_edge`` guarantees at most one edge per (src, dst, rel_type) triple.
    When a duplicate is detected the existing edge's props are updated; if a
    ``weight`` key is present in *both* old and new props the values are summed.
    """

    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _node_to_data(self, node_id: str) -> NodeData:
        """Convert a networkx node to :class:`NodeData`."""
        attrs: dict[str, Any] = dict(self._g.nodes[node_id])
        labels: list[str] = attrs.pop("_labels", [])
        return NodeData(node_id=node_id, labels=labels, props=attrs)

    def _find_edge_key(self, src: str, dst: str, rel_type: str) -> Any:
        """Return the MultiDiGraph edge key for (src, dst, rel_type) or None."""
        if not self._g.has_node(src) or not self._g.has_node(dst):
            return None
        if src not in self._g or dst not in self._g[src]:
            return None
        for key, data in self._g[src][dst].items():
            if data.get("rel_type") == rel_type:
                return key
        return None

    # ------------------------------------------------------------------
    # AbstractGraphBackend implementation
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        node_id: str,
        labels: list[str],
        props: dict[str, Any],
    ) -> None:
        """Insert or merge-update a node.

        When the node already exists, incoming *props* are merged on top of
        existing attributes; incoming *labels* are unioned with existing ones.
        """
        if self._g.has_node(node_id):
            existing: dict[str, Any] = self._g.nodes[node_id]
            # Merge labels (union, preserve order — new ones appended)
            existing_labels: list[str] = existing.get("_labels", [])
            for lbl in labels:
                if lbl not in existing_labels:
                    existing_labels.append(lbl)
            existing["_labels"] = existing_labels
            # Merge props
            existing.update(props)
        else:
            self._g.add_node(node_id, _labels=list(labels), **props)

    async def upsert_edge(
        self,
        src: str,
        dst: str,
        rel_type: str,
        props: dict[str, Any],
    ) -> None:
        """Insert or update a directed edge, deduplicating by rel_type.

        If an edge src→dst with *rel_type* already exists its ``props`` dict
        is updated.  If both old and new props contain a numeric ``weight``
        key the values are *summed* (accumulates interaction counts).

        Nodes are auto-created (with empty labels/props) when missing, so
        callers may add edges before full node data is available.
        """
        # Ensure both endpoints exist so networkx doesn't silently create them
        # without our _labels attribute.
        for node_id in (src, dst):
            if not self._g.has_node(node_id):
                self._g.add_node(node_id, _labels=[], **{})

        existing_key = self._find_edge_key(src, dst, rel_type)
        if existing_key is not None:
            existing_props: dict[str, Any] = self._g[src][dst][existing_key]["props"]  # type: ignore[index]
            # Merge tweet_ids (union, capped at 20) before applying other props.
            incoming_tids: list = props.get("tweet_ids") or []
            if incoming_tids:
                old_tids: list = existing_props.get("tweet_ids") or []
                props = dict(props)
                props["tweet_ids"] = list(dict.fromkeys(old_tids + incoming_tids))[:20]
            # Accumulate weight if both sides carry it
            if "weight" in existing_props and "weight" in props:
                merged = dict(existing_props)
                merged.update(props)
                merged["weight"] = existing_props["weight"] + props["weight"]
                self._g[src][dst][existing_key]["props"] = merged  # type: ignore[index]
            else:
                existing_props.update(props)
        else:
            self._g.add_edge(src, dst, rel_type=rel_type, props=dict(props))

    async def get_neighbors(
        self,
        node_id: str,
        rel_types: list[str] | None = None,
        depth: int = 1,
    ) -> list[NodeData]:
        """BFS from *node_id* up to *depth* hops.

        When *rel_types* is provided only edges whose ``rel_type`` attribute
        matches one of the listed values are traversed.  Returns a deduplicated
        list of :class:`NodeData` dicts (the seed node is excluded).
        """
        if not self._g.has_node(node_id):
            return []

        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier:
                for successor in self._g.successors(current):
                    if successor in visited:
                        continue
                    # Check at least one edge passes the rel_type filter
                    if rel_types is not None:
                        passes = any(
                            data.get("rel_type") in rel_types
                            for data in self._g[current][successor].values()
                        )
                        if not passes:
                            continue
                    next_frontier.add(successor)
                    visited.add(successor)
            frontier = next_frontier
            if not frontier:
                break

        visited.discard(node_id)
        return [self._node_to_data(n) for n in visited if self._g.has_node(n)]

    async def get_subgraph(
        self,
        node_id: str,
        depth: int,
        limit: int,
    ) -> GraphData:
        """BFS subgraph rooted at *node_id*.

        Collects at most *limit* nodes (including the seed).  All edges between
        collected nodes — regardless of direction — are included in the result.

        Returns a :class:`GraphData` with ``nodes`` and ``edges`` lists.
        """
        if not self._g.has_node(node_id):
            return GraphData(nodes=[], edges=[])

        visited_nodes: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue and len(visited_nodes) < limit:
            current, current_depth = queue.popleft()
            if current in visited_nodes:
                continue
            visited_nodes.add(current)
            if current_depth >= depth:
                continue
            for successor in self._g.successors(current):
                if successor not in visited_nodes and len(visited_nodes) < limit:
                    queue.append((successor, current_depth + 1))

        # Build node list
        nodes: list[NodeData] = [
            self._node_to_data(n) for n in visited_nodes if self._g.has_node(n)
        ]

        # Collect all edges where both endpoints are in visited_nodes
        edges: list[EdgeData] = []
        for src in visited_nodes:
            if not self._g.has_node(src):
                continue
            for dst in self._g.successors(src):
                if dst not in visited_nodes:
                    continue
                for edge_data in self._g[src][dst].values():
                    edges.append(
                        EdgeData(
                            src=src,
                            dst=dst,
                            rel_type=edge_data.get("rel_type", ""),
                            props=dict(edge_data.get("props", {})),
                        )
                    )

        return GraphData(nodes=nodes, edges=edges)

    async def run_cypher(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Not supported — raises :class:`NotImplementedError`."""
        raise NotImplementedError(
            "networkx backend does not support Cypher. "
            "Use run_nx_query() for arbitrary graph operations, "
            "or switch to the Neo4j backend."
        )

    async def run_nx_query(self, fn: Callable[..., Any]) -> Any:
        """Execute *fn(graph)* against the underlying MultiDiGraph.

        Allows callers to run arbitrary networkx algorithms without exposing
        the private ``_g`` attribute directly.

        Example::

            result = await backend.run_nx_query(
                lambda g: nx.pagerank(g)
            )
        """
        return fn(self._g)

    async def node_count(self) -> int:
        """Return the number of nodes currently in the graph."""
        return len(self._g.nodes)

    async def edge_count(self) -> int:
        """Return the total number of directed edges (including parallel edges)."""
        return len(self._g.edges)

    async def save(self, path: str) -> None:
        """Persist the graph to *path*.

        - ``*.pkl`` → Python pickle (fast, binary, not human-readable)
        - anything else → GraphML XML (portable, text-based)

        Parent directories are created automatically.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.suffix.lower() == ".pkl":
            with p.open("wb") as fh:
                pickle.dump(self._g, fh, protocol=pickle.HIGHEST_PROTOCOL)
        else:
            # GraphML only supports primitive scalars.
            # Encode list/dict node attrs as JSON strings; mark with __json__ prefix.
            g_export = copy.deepcopy(self._g)
            for nid in g_export.nodes:
                attrs = g_export.nodes[nid]
                for k in list(attrs):
                    if isinstance(attrs[k], (list, dict)):
                        attrs[f"__json__{k}"] = json.dumps(attrs[k])
                        del attrs[k]
            for src, dst, key in g_export.edges(keys=True):
                attrs = g_export[src][dst][key]
                for k in list(attrs):
                    if isinstance(attrs[k], (list, dict)):
                        attrs[f"__json__{k}"] = json.dumps(attrs[k])
                        del attrs[k]
            nx.write_graphml(g_export, str(p))

    async def load(self, path: str) -> None:
        """Replace the current in-memory graph with data from *path*.

        Format is inferred from the file extension (same rules as :meth:`save`).
        Raises :class:`FileNotFoundError` when *path* does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Graph file not found: {path!r}")

        if p.suffix.lower() == ".pkl":
            with p.open("rb") as fh:
                loaded = pickle.load(fh)
            if not isinstance(loaded, nx.MultiDiGraph):
                raise TypeError(
                    f"Pickled object is {type(loaded).__name__}, "
                    "expected nx.MultiDiGraph"
                )
            self._g = loaded
        else:
            loaded_g = nx.read_graphml(str(p), node_type=str)
            if not isinstance(loaded_g, nx.MultiDiGraph):
                loaded_g = nx.MultiDiGraph(loaded_g)
            # Decode __json__-prefixed attrs back to list/dict
            for nid in loaded_g.nodes:
                attrs = loaded_g.nodes[nid]
                for k in list(attrs):
                    if k.startswith("__json__"):
                        real_key = k[len("__json__"):]
                        attrs[real_key] = json.loads(attrs.pop(k))
            for src, dst, key in loaded_g.edges(keys=True):
                attrs = loaded_g[src][dst][key]
                for k in list(attrs):
                    if k.startswith("__json__"):
                        real_key = k[len("__json__"):]
                        attrs[real_key] = json.loads(attrs.pop(k))
            self._g = loaded_g
