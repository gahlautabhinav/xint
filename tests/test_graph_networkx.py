from __future__ import annotations

from pathlib import Path

import pytest

from graph.algorithms.traversal import bfs, dfs
from graph.backends.neo4j_backend import Neo4jBackend
from graph.backends.networkx_backend import NetworkxBackend
from graph.schema.edges import FOLLOWS, MENTIONS
from graph.schema.nodes import make_node_id, parse_node_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend() -> NetworkxBackend:
    return NetworkxBackend()


async def _seed_graph(b: NetworkxBackend) -> None:
    """Build a small graph: alice → bob → carol, alice → carol (MENTIONS)."""
    alice = make_node_id("twitter", "alice")
    bob = make_node_id("twitter", "bob")
    carol = make_node_id("twitter", "carol")
    await b.upsert_node(alice, ["Account"], {"followers_count": 100})
    await b.upsert_node(bob, ["Account"], {"followers_count": 50})
    await b.upsert_node(carol, ["Account"], {"followers_count": 200})
    await b.upsert_edge(alice, bob, FOLLOWS, {"weight": 1.0})
    await b.upsert_edge(bob, carol, FOLLOWS, {"weight": 1.0})
    await b.upsert_edge(alice, carol, MENTIONS, {"weight": 1.0})


# ---------------------------------------------------------------------------
# node_id schema helpers
# ---------------------------------------------------------------------------

class TestNodeIdHelpers:
    def test_make_node_id_adds_at(self):
        assert make_node_id("twitter", "alice") == "twitter:@alice"

    def test_make_node_id_preserves_at(self):
        assert make_node_id("twitter", "@alice") == "twitter:@alice"

    def test_make_node_id_lowercases(self):
        assert make_node_id("Twitter", "Alice") == "twitter:@alice"

    def test_parse_node_id(self):
        platform, handle = parse_node_id("twitter:@alice")
        assert platform == "twitter"
        assert handle == "@alice"

    def test_parse_node_id_invalid(self):
        with pytest.raises(ValueError):
            parse_node_id("nocohere")


# ---------------------------------------------------------------------------
# NetworkxBackend — upsert_node
# ---------------------------------------------------------------------------

class TestUpsertNode:
    async def test_insert_new_node(self):
        b = _make_backend()
        nid = make_node_id("twitter", "alice")
        await b.upsert_node(nid, ["Account"], {"bio": "hello"})
        assert await b.node_count() == 1

    async def test_upsert_merges_props(self):
        b = _make_backend()
        nid = make_node_id("twitter", "alice")
        await b.upsert_node(nid, ["Account"], {"followers_count": 10})
        await b.upsert_node(nid, ["Account"], {"following_count": 5})
        nodes = (await b.get_subgraph(nid, depth=0, limit=1))["nodes"]
        assert nodes[0]["props"]["followers_count"] == 10
        assert nodes[0]["props"]["following_count"] == 5

    async def test_upsert_unions_labels(self):
        b = _make_backend()
        nid = make_node_id("twitter", "alice")
        await b.upsert_node(nid, ["Account"], {})
        await b.upsert_node(nid, ["Seed"], {})
        nodes = (await b.get_subgraph(nid, depth=0, limit=1))["nodes"]
        assert "Account" in nodes[0]["labels"]
        assert "Seed" in nodes[0]["labels"]

    async def test_idempotent(self):
        b = _make_backend()
        nid = make_node_id("twitter", "alice")
        await b.upsert_node(nid, ["Account"], {"x": 1})
        await b.upsert_node(nid, ["Account"], {"x": 1})
        assert await b.node_count() == 1


# ---------------------------------------------------------------------------
# NetworkxBackend — upsert_edge
# ---------------------------------------------------------------------------

class TestUpsertEdge:
    async def test_insert_edge(self):
        b = _make_backend()
        await _seed_graph(b)
        assert await b.edge_count() == 3

    async def test_dedup_same_rel_type(self):
        b = _make_backend()
        alice = make_node_id("twitter", "alice")
        bob = make_node_id("twitter", "bob")
        await b.upsert_edge(alice, bob, FOLLOWS, {"weight": 1.0})
        await b.upsert_edge(alice, bob, FOLLOWS, {"weight": 1.0})
        assert await b.edge_count() == 1

    async def test_weight_accumulates(self):
        b = _make_backend()
        alice = make_node_id("twitter", "alice")
        bob = make_node_id("twitter", "bob")
        await b.upsert_edge(alice, bob, MENTIONS, {"weight": 2.0})
        await b.upsert_edge(alice, bob, MENTIONS, {"weight": 3.0})
        sg = await b.get_subgraph(alice, depth=1, limit=10)
        edge = next(e for e in sg["edges"] if e["rel_type"] == MENTIONS)
        assert edge["props"]["weight"] == pytest.approx(5.0)

    async def test_different_rel_types_not_deduped(self):
        b = _make_backend()
        alice = make_node_id("twitter", "alice")
        bob = make_node_id("twitter", "bob")
        await b.upsert_edge(alice, bob, FOLLOWS, {})
        await b.upsert_edge(alice, bob, MENTIONS, {})
        assert await b.edge_count() == 2

    async def test_autocreates_missing_nodes(self):
        b = _make_backend()
        alice = make_node_id("twitter", "alice")
        bob = make_node_id("twitter", "bob")
        await b.upsert_edge(alice, bob, FOLLOWS, {})
        assert await b.node_count() == 2


# ---------------------------------------------------------------------------
# NetworkxBackend — get_neighbors
# ---------------------------------------------------------------------------

class TestGetNeighbors:
    async def test_depth_1(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        neighbors = await b.get_neighbors(alice, depth=1)
        handles = {n["node_id"] for n in neighbors}
        assert make_node_id("twitter", "bob") in handles
        assert make_node_id("twitter", "carol") in handles

    async def test_depth_2(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        # at depth 1: bob, carol. at depth 2: carol already visited via alice→carol
        neighbors = await b.get_neighbors(alice, depth=2)
        assert len(neighbors) >= 2

    async def test_rel_type_filter(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        # Only FOLLOWS edges: should get bob (alice→bob FOLLOWS), NOT carol via MENTIONS
        neighbors = await b.get_neighbors(alice, rel_types=[FOLLOWS], depth=1)
        handles = {n["node_id"] for n in neighbors}
        assert make_node_id("twitter", "bob") in handles
        assert make_node_id("twitter", "carol") not in handles

    async def test_missing_node_returns_empty(self):
        b = _make_backend()
        assert await b.get_neighbors("twitter:@nobody") == []


# ---------------------------------------------------------------------------
# NetworkxBackend — get_subgraph
# ---------------------------------------------------------------------------

class TestGetSubgraph:
    async def test_depth_cap(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        # depth=1 from alice: alice + bob + carol (alice→bob, alice→carol direct)
        sg = await b.get_subgraph(alice, depth=1, limit=100)
        node_ids = {n["node_id"] for n in sg["nodes"]}
        assert alice in node_ids
        assert make_node_id("twitter", "bob") in node_ids

    async def test_limit_nodes(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        sg = await b.get_subgraph(alice, depth=3, limit=2)
        assert len(sg["nodes"]) <= 2

    async def test_includes_edges(self):
        b = _make_backend()
        await _seed_graph(b)
        alice = make_node_id("twitter", "alice")
        sg = await b.get_subgraph(alice, depth=2, limit=100)
        assert len(sg["edges"]) > 0

    async def test_missing_node_returns_empty(self):
        b = _make_backend()
        sg = await b.get_subgraph("twitter:@nobody", depth=2, limit=100)
        assert sg["nodes"] == []
        assert sg["edges"] == []


# ---------------------------------------------------------------------------
# NetworkxBackend — counts
# ---------------------------------------------------------------------------

class TestCounts:
    async def test_node_count(self):
        b = _make_backend()
        await _seed_graph(b)
        assert await b.node_count() == 3

    async def test_edge_count(self):
        b = _make_backend()
        await _seed_graph(b)
        assert await b.edge_count() == 3

    async def test_empty_counts(self):
        b = _make_backend()
        assert await b.node_count() == 0
        assert await b.edge_count() == 0


# ---------------------------------------------------------------------------
# NetworkxBackend — run_nx_query / run_cypher
# ---------------------------------------------------------------------------

class TestQueries:
    async def test_run_nx_query(self):
        b = _make_backend()
        await _seed_graph(b)
        count = await b.run_nx_query(lambda g: g.number_of_nodes())
        assert count == 3

    async def test_run_cypher_raises(self):
        b = _make_backend()
        with pytest.raises(NotImplementedError):
            await b.run_cypher("MATCH (n) RETURN n", {})


# ---------------------------------------------------------------------------
# NetworkxBackend — save / load (pickle + graphml)
# ---------------------------------------------------------------------------

class TestPersistence:
    async def test_pickle_round_trip(self, tmp_path: Path):
        b = _make_backend()
        await _seed_graph(b)
        path = str(tmp_path / "graph.pkl")
        await b.save(path)
        b2 = _make_backend()
        await b2.load(path)
        assert await b2.node_count() == 3
        assert await b2.edge_count() == 3

    async def test_graphml_round_trip(self, tmp_path: Path):
        b = _make_backend()
        await _seed_graph(b)
        path = str(tmp_path / "graph.graphml")
        await b.save(path)
        b2 = _make_backend()
        await b2.load(path)
        assert await b2.node_count() == 3

    async def test_load_missing_file_raises(self, tmp_path: Path):
        b = _make_backend()
        with pytest.raises(FileNotFoundError):
            await b.load(str(tmp_path / "nonexistent.pkl"))

    async def test_save_creates_parent_dirs(self, tmp_path: Path):
        b = _make_backend()
        await _seed_graph(b)
        nested = str(tmp_path / "a" / "b" / "c" / "graph.pkl")
        await b.save(nested)
        assert Path(nested).exists()


# ---------------------------------------------------------------------------
# BFS / DFS traversal
# ---------------------------------------------------------------------------

class TestTraversal:
    def _build_graph(self) -> object:
        import networkx as nx
        g = nx.MultiDiGraph()
        # a→b→c→d, a→c
        for node in "abcd":
            g.add_node(node)
        g.add_edge("a", "b", rel_type=FOLLOWS, props={})
        g.add_edge("b", "c", rel_type=FOLLOWS, props={})
        g.add_edge("c", "d", rel_type=FOLLOWS, props={})
        g.add_edge("a", "c", rel_type=MENTIONS, props={})
        return g

    def test_bfs_depth_cap(self):
        g = self._build_graph()
        # Graph: a→b, b→c, c→d, a→c (shortcut via MENTIONS)
        # BFS depth=1 from a: direct neighbors only
        result = bfs(g, "a", max_depth=1)
        assert result["a"] == 0
        assert result["b"] == 1   # a→b direct
        assert result["c"] == 1   # a→c direct (MENTIONS)
        assert "d" not in result  # depth 2+ from a, capped at 1

    def test_bfs_visit_cap(self):
        g = self._build_graph()
        result = bfs(g, "a", max_visits=2)
        assert len(result) <= 2

    def test_bfs_rel_type_filter(self):
        g = self._build_graph()
        # Only FOLLOWS: a→b→c→d. MENTIONS (a→c) ignored.
        result = bfs(g, "a", max_depth=3, rel_types=[FOLLOWS])
        assert "b" in result
        assert "c" in result

    def test_bfs_missing_start(self):
        g = self._build_graph()
        assert bfs(g, "z") == {}

    def test_dfs_visits_all(self):
        g = self._build_graph()
        result = dfs(g, "a", max_depth=3)
        assert "a" in result
        assert "b" in result
        assert "d" in result

    def test_dfs_depth_cap(self):
        g = self._build_graph()
        result = dfs(g, "a", max_depth=1)
        assert "a" in result
        # depth=1: only direct successors of a
        for _node, depth in result.items():
            assert depth <= 1

    def test_dfs_visit_cap(self):
        g = self._build_graph()
        result = dfs(g, "a", max_visits=2)
        assert len(result) <= 2

    def test_dfs_missing_start(self):
        g = self._build_graph()
        assert dfs(g, "z") == {}


# ---------------------------------------------------------------------------
# Neo4j stub
# ---------------------------------------------------------------------------

class TestNeo4jStub:
    async def test_all_methods_raise(self):
        b = Neo4jBackend(url="bolt://localhost:7687", user="neo4j", password="x")
        for coro in [
            b.upsert_node("n", [], {}),
            b.upsert_edge("a", "b", FOLLOWS, {}),
            b.get_neighbors("n"),
            b.get_subgraph("n", 1, 10),
            b.run_cypher("", {}),
            b.run_nx_query(lambda g: g),
            b.node_count(),
            b.edge_count(),
            b.save("/tmp/x"),
            b.load("/tmp/x"),
        ]:
            with pytest.raises(NotImplementedError):
                await coro
