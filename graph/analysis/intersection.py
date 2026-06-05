"""Network intersection / similarity analysis.

Given ≥2 BFS subgraph snapshots (one per seed), surfaces:
- common nodes (accounts in ≥2 networks), sorted by membership count
- pairwise Jaccard similarity scores
- shared direct followings per seed pair
- a combined node+edge list for frontend visualisation
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

__all__ = [
    "CommonNode",
    "PairwiseSimilarity",
    "IntersectionResult",
    "compute_intersection",
    "combined_graph",
]


def _handle_from_id(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


@dataclass
class CommonNode:
    node_id: str
    handle: str
    in_seeds: list[str]  # seed handles that contain this node (≥2)
    props: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "handle": self.handle,
            "in_seeds": self.in_seeds,
            "props": self.props,
        }


@dataclass
class PairwiseSimilarity:
    seed_a: str
    seed_b: str
    jaccard: float
    common_count: int
    union_count: int
    common_followings: int  # nodes both seeds FOLLOW directly

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_a": self.seed_a,
            "seed_b": self.seed_b,
            "jaccard": self.jaccard,
            "common_count": self.common_count,
            "union_count": self.union_count,
            "common_followings": self.common_followings,
        }


@dataclass
class IntersectionResult:
    seeds: list[str]
    common_nodes: list[CommonNode]
    pairwise: list[PairwiseSimilarity]


def compute_intersection(
    seed_handles: list[str],
    seed_networks: list[dict[str, Any]],
) -> IntersectionResult:
    """Compute intersection of ≥2 seed networks.

    Parameters
    ----------
    seed_handles:
        Bare handles (e.g. ["elonmusk", "sama"]).  Length must match
        ``seed_networks``.
    seed_networks:
        One GraphData dict per seed — each has ``"nodes"`` and ``"edges"``
        lists as returned by ``AbstractGraphBackend.get_subgraph``.
    """
    assert len(seed_handles) == len(seed_networks), "handles/networks length mismatch"

    # node_id → list of seed handles that contain it
    node_to_seeds: dict[str, list[str]] = {}
    node_props: dict[str, dict[str, Any]] = {}

    # direct followings per seed (FOLLOWS edges FROM the seed node)
    followings: list[set[str]] = []

    for handle, network in zip(seed_handles, seed_networks, strict=False):
        seed_id = f"twitter:{handle}"

        for node in network.get("nodes", []):
            nid: str = node["node_id"]
            if nid not in node_to_seeds:
                node_to_seeds[nid] = []
            node_to_seeds[nid].append(handle)
            node_props[nid] = node.get("props", {})

        seed_followings: set[str] = set()
        for edge in network.get("edges", []):
            if edge.get("rel_type") == "FOLLOWS" and edge.get("src") == seed_id:
                seed_followings.add(edge["dst"])
        followings.append(seed_followings)

    seed_ids = {f"twitter:{h}" for h in seed_handles}

    # Common nodes: appear in ≥2 seed networks, not a seed themselves
    common_nodes: list[CommonNode] = []
    for nid, in_seeds in node_to_seeds.items():
        if len(in_seeds) >= 2 and nid not in seed_ids:
            common_nodes.append(
                CommonNode(
                    node_id=nid,
                    handle=_handle_from_id(nid),
                    in_seeds=in_seeds,
                    props=node_props.get(nid, {}),
                )
            )
    # Sort: most-shared first, then alphabetical for stability
    common_nodes.sort(key=lambda n: (-len(n.in_seeds), n.handle))

    # Per-seed node sets (excluding the seed itself)
    node_sets: list[set[str]] = []
    for handle, network in zip(seed_handles, seed_networks, strict=False):
        seed_id = f"twitter:{handle}"
        ids = {n["node_id"] for n in network.get("nodes", [])} - {seed_id}
        node_sets.append(ids)

    # Pairwise similarities
    pairwise: list[PairwiseSimilarity] = []
    for (i, a_handle), (j, b_handle) in combinations(enumerate(seed_handles), 2):
        a_ids = node_sets[i]
        b_ids = node_sets[j]
        inter = a_ids & b_ids
        union = a_ids | b_ids
        jaccard = round(len(inter) / len(union), 4) if union else 0.0
        pairwise.append(
            PairwiseSimilarity(
                seed_a=a_handle,
                seed_b=b_handle,
                jaccard=jaccard,
                common_count=len(inter),
                union_count=len(union),
                common_followings=len(followings[i] & followings[j]),
            )
        )

    return IntersectionResult(
        seeds=seed_handles,
        common_nodes=common_nodes,
        pairwise=pairwise,
    )


def combined_graph(
    seed_handles: list[str],
    seed_networks: list[dict[str, Any]],
    common_node_ids: set[str],
    limit: int = 300,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build node+edge lists for visualisation.

    Includes only seed nodes + common nodes and edges between them.
    Each node gets a ``membership`` prop (list of seed handles) and
    an ``is_seed`` bool prop.
    """
    seed_ids = {f"twitter:{h}" for h in seed_handles}
    keep_ids = seed_ids | common_node_ids

    nodes_by_id: dict[str, dict[str, Any]] = {}
    membership: dict[str, list[str]] = {nid: [] for nid in keep_ids}

    for handle, network in zip(seed_handles, seed_networks, strict=False):
        for node in network.get("nodes", []):
            nid: str = node["node_id"]
            if nid not in keep_ids:
                continue
            if nid not in nodes_by_id:
                nodes_by_id[nid] = {
                    "node_id": nid,
                    "labels": node.get("labels", []),
                    "props": dict(node.get("props", {})),
                }
            if handle not in membership[nid]:
                membership[nid].append(handle)

    for nid, node in nodes_by_id.items():
        node["props"]["membership"] = membership.get(nid, [])
        node["props"]["is_seed"] = nid in seed_ids

    seen_edges: set[str] = set()
    edges: list[dict[str, Any]] = []
    for network in seed_networks:
        for edge in network.get("edges", []):
            src, dst = edge["src"], edge["dst"]
            if src in keep_ids and dst in keep_ids:
                eid = f"{src}__{edge['rel_type']}__{dst}"
                if eid not in seen_edges:
                    seen_edges.add(eid)
                    edges.append(edge)

    return list(nodes_by_id.values())[:limit], edges
