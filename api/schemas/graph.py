from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class NodeResponse(BaseModel):
    node_id: str
    labels: list[str]
    props: dict[str, Any]


class EdgeResponse(BaseModel):
    src: str
    dst: str
    rel_type: str
    props: dict[str, Any]


class SubgraphResponse(BaseModel):
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]


class NeighborsResponse(BaseModel):
    node_id: str
    neighbors: list[NodeResponse]


class HashtagCount(BaseModel):
    tag: str
    count: int


class HashtagPairResponse(BaseModel):
    source: str
    target: str
    shared: list[str]
    weight: int


class HashtagAnalysisResponse(BaseModel):
    account_count: int               # accounts that had >=1 hashtag
    top_hashtags: list[HashtagCount]
    pairs: list[HashtagPairResponse]  # accounts sharing hashtags


class CommonNodeResponse(BaseModel):
    node_id: str
    handle: str
    in_seeds: list[str]
    props: dict[str, Any]


class PairwiseSimilarityResponse(BaseModel):
    seed_a: str
    seed_b: str
    jaccard: float
    common_count: int
    union_count: int
    common_followings: int


class IntersectionResponse(BaseModel):
    seeds: list[str]
    common_nodes: list[CommonNodeResponse]
    pairwise: list[PairwiseSimilarityResponse]
    combined_nodes: list[NodeResponse]
    combined_edges: list[EdgeResponse]
