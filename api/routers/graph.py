from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, GraphBackend
from api.schemas.graph import (
    EdgeResponse,
    NeighborsResponse,
    NodeResponse,
    SubgraphResponse,
)
from graph.schema.nodes import make_node_id

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{handle}/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    handle: str,
    _key: ApiKeyCheck,
    graph: GraphBackend,
    depth: int = Query(default=2, ge=1, le=4),
    limit: int = Query(default=200, ge=1, le=1000),
    platform: str = Query(default="twitter"),
) -> SubgraphResponse:
    """Return a BFS subgraph rooted at the given handle."""
    node_id = make_node_id(platform, handle)
    data = await graph.get_subgraph(node_id, depth=depth, limit=limit)

    nodes = [NodeResponse(node_id=n["node_id"], labels=n["labels"], props=n["props"]) for n in data["nodes"]]
    edges = [EdgeResponse(src=e["src"], dst=e["dst"], rel_type=e["rel_type"], props=e["props"]) for e in data["edges"]]

    if not nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {platform}/{handle} not found in graph",
        )
    return SubgraphResponse(nodes=nodes, edges=edges)


@router.get("/{handle}/neighbors", response_model=NeighborsResponse)
async def get_neighbors(
    handle: str,
    _key: ApiKeyCheck,
    graph: GraphBackend,
    depth: int = Query(default=1, ge=1, le=3),
    rel_types: list[str] | None = Query(default=None),  # noqa: B008
    platform: str = Query(default="twitter"),
) -> NeighborsResponse:
    """Return direct (or multi-hop) neighbors of the given handle."""
    node_id = make_node_id(platform, handle)
    neighbors = await graph.get_neighbors(node_id, rel_types=rel_types, depth=depth)
    return NeighborsResponse(
        node_id=node_id,
        neighbors=[NodeResponse(node_id=n["node_id"], labels=n["labels"], props=n["props"]) for n in neighbors],
    )
