from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import ApiKeyCheck, DbSession, GraphBackend
from api.schemas.graph import (
    CommonNodeResponse,
    EdgeResponse,
    HashtagAnalysisResponse,
    HashtagCount,
    HashtagPairResponse,
    IntersectionResponse,
    NeighborsResponse,
    NodeResponse,
    PairwiseSimilarityResponse,
    SubgraphResponse,
)
from graph.analysis.hashtags import cooccurrence, tags_by_account, top_hashtags
from graph.analysis.intersection import combined_graph, compute_intersection
from graph.schema.nodes import make_node_id
from storage.repositories.account_repo import AccountRepository

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/hashtags", response_model=HashtagAnalysisResponse)
async def get_hashtag_analysis(
    _key: ApiKeyCheck,
    session: DbSession,
    limit: int = Query(default=25, ge=1, le=100),
    min_shared: int = Query(default=1, ge=1, le=10),
) -> HashtagAnalysisResponse:
    """Global hashtag ranking + account pairs that share hashtags (interest overlay)."""
    accounts = await AccountRepository(session).all()
    tag_map = tags_by_account(accounts)
    tops = top_hashtags(tag_map, limit=limit)
    pairs = cooccurrence(tag_map, min_shared=min_shared)
    return HashtagAnalysisResponse(
        account_count=len(tag_map),
        top_hashtags=[HashtagCount(tag=t, count=c) for t, c in tops],
        pairs=[HashtagPairResponse(**p.to_dict()) for p in pairs],
    )


@router.get("/intersection", response_model=IntersectionResponse)
async def get_intersection(
    _key: ApiKeyCheck,
    graph: GraphBackend,
    seeds: list[str] = Query(...),  # noqa: B008
    depth: int = Query(default=2, ge=1, le=5),
    limit: int = Query(default=200, ge=1, le=500),
    platform: str = Query(default="twitter"),
) -> IntersectionResponse:
    """Find common nodes and similarity between ≥2 seed networks."""
    if len(seeds) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least 2 seeds required")
    if len(seeds) > 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 6 seeds")

    networks: list[dict] = []
    valid_seeds: list[str] = []
    for seed in seeds:
        node_id = make_node_id(platform, seed)
        data = await graph.get_subgraph(node_id, depth=depth, limit=limit)
        if data["nodes"]:
            networks.append(dict(data))
            valid_seeds.append(seed)

    if len(valid_seeds) < 2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fewer than 2 seeds found in graph — crawl them first",
        )

    result = compute_intersection(valid_seeds, networks)
    common_ids = {n.node_id for n in result.common_nodes}
    comb_nodes, comb_edges = combined_graph(valid_seeds, networks, common_ids)

    return IntersectionResponse(
        seeds=result.seeds,
        common_nodes=[CommonNodeResponse(**n.to_dict()) for n in result.common_nodes],
        pairwise=[PairwiseSimilarityResponse(**p.to_dict()) for p in result.pairwise],
        combined_nodes=[
            NodeResponse(node_id=n["node_id"], labels=n["labels"], props=n["props"])
            for n in comb_nodes
        ],
        combined_edges=[
            EdgeResponse(src=e["src"], dst=e["dst"], rel_type=e["rel_type"], props=e.get("props", {}))
            for e in comb_edges
        ],
    )


@router.get("/{handle}/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    handle: str,
    _key: ApiKeyCheck,
    graph: GraphBackend,
    depth: int = Query(default=2, ge=1, le=20),
    limit: int = Query(default=200, ge=1, le=10000),
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
