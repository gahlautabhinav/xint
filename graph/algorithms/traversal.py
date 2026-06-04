from __future__ import annotations

from collections import deque

import networkx as nx


def bfs(
    graph: nx.MultiDiGraph,
    start: str,
    max_depth: int = 3,
    max_visits: int = 1000,
    rel_types: list[str] | None = None,
) -> dict[str, int]:
    """Breadth-first search from *start*.

    Traverses outgoing edges only (following directed graph direction).
    When *rel_types* is provided an edge is traversed only if its
    ``rel_type`` attribute matches one of the listed values.

    Parameters
    ----------
    graph:
        The :class:`~networkx.MultiDiGraph` to traverse.
    start:
        Seed node_id.  Returns ``{}`` immediately when not in the graph.
    max_depth:
        Hard upper bound on hop distance from *start*.  Nodes at exactly
        *max_depth* are recorded but their successors are not expanded.
    max_visits:
        Hard upper bound on the total number of nodes returned (including
        *start*).  The BFS terminates as soon as this limit is reached.
    rel_types:
        Optional whitelist of relationship types.  ``None`` means all edges.

    Returns
    -------
    dict[str, int]
        Mapping ``{node_id: depth_from_start}``.  The seed node itself is
        included at depth 0.
    """
    if not graph.has_node(start):
        return {}

    visited: dict[str, int] = {start: 0}
    queue: deque[tuple[str, int]] = deque([(start, 0)])

    while queue and len(visited) < max_visits:
        current, current_depth = queue.popleft()
        if current_depth >= max_depth:
            continue
        for successor in graph.successors(current):
            if successor in visited:
                continue
            # Edge filter — at least one edge on this hop must match
            if rel_types is not None:
                passes = any(
                    data.get("rel_type") in rel_types
                    for data in graph[current][successor].values()
                )
                if not passes:
                    continue
            if len(visited) >= max_visits:
                break
            visited[successor] = current_depth + 1
            queue.append((successor, current_depth + 1))

    return visited


def dfs(
    graph: nx.MultiDiGraph,
    start: str,
    max_depth: int = 3,
    max_visits: int = 1000,
    rel_types: list[str] | None = None,
) -> dict[str, int]:
    """Depth-first search from *start*.

    Traverses outgoing edges only (following directed graph direction).
    When *rel_types* is provided an edge is traversed only if its
    ``rel_type`` attribute matches one of the listed values.

    DFS records the *first* depth at which each node is discovered — this
    may differ from BFS shortest-path depth but is consistent within a
    single DFS traversal.

    Parameters
    ----------
    graph:
        The :class:`~networkx.MultiDiGraph` to traverse.
    start:
        Seed node_id.  Returns ``{}`` immediately when not in the graph.
    max_depth:
        Hard upper bound on recursion depth from *start*.
    max_visits:
        Hard upper bound on the total number of nodes recorded.
    rel_types:
        Optional whitelist of relationship types.  ``None`` means all edges.

    Returns
    -------
    dict[str, int]
        Mapping ``{node_id: depth_from_start}``.  The seed node itself is
        included at depth 0.
    """
    if not graph.has_node(start):
        return {}

    visited: dict[str, int] = {}
    # Stack entries: (node_id, depth)
    # Use a list as an explicit stack so we avoid Python recursion limits on
    # large graphs.
    stack: list[tuple[str, int]] = [(start, 0)]

    while stack and len(visited) < max_visits:
        current, current_depth = stack.pop()
        if current in visited:
            continue
        visited[current] = current_depth
        if current_depth >= max_depth:
            continue
        # Push successors in reverse order so that the first successor in
        # adjacency order is explored first (matches intuitive DFS order).
        successors = list(graph.successors(current))
        for successor in reversed(successors):
            if successor in visited:
                continue
            # Edge filter
            if rel_types is not None:
                passes = any(
                    data.get("rel_type") in rel_types
                    for data in graph[current][successor].values()
                )
                if not passes:
                    continue
            if len(visited) < max_visits:
                stack.append((successor, current_depth + 1))

    return visited
