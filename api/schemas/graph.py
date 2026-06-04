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
