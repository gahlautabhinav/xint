from __future__ import annotations

from types import SimpleNamespace

from graph.analysis.hashtags import (
    HashtagPair,
    _hashtags_of,
    cooccurrence,
    tags_by_account,
    top_hashtags,
)
from graph.analysis.intersection import (
    combined_graph,
    compute_intersection,
)
from scraper.analysis.geo import (
    normalize_location,
    tz_offset_to_lon,
)
from scraper.analysis.timezone import (
    TimezoneEstimate,
    _parse_hour_utc,
    _sleep_window_start,
    infer_timezone,
)

# ---------------------------------------------------------------------------
# timezone: _parse_hour_utc
# ---------------------------------------------------------------------------


class TestParseHourUtc:
    def test_z_suffix_utc(self):
        assert _parse_hour_utc("2024-01-01T10:00:00.000Z") == 10

    def test_offset_converted_to_utc(self):
        # 10:00 at +02:00 is 08:00 UTC
        assert _parse_hour_utc("2024-01-01T10:00:00+02:00") == 8

    def test_no_fraction(self):
        assert _parse_hour_utc("2024-06-05T23:15:00Z") == 23

    def test_none(self):
        assert _parse_hour_utc(None) is None

    def test_empty(self):
        assert _parse_hour_utc("") is None

    def test_garbage(self):
        assert _parse_hour_utc("not-a-date") is None


# ---------------------------------------------------------------------------
# timezone: _sleep_window_start
# ---------------------------------------------------------------------------


class TestSleepWindowStart:
    def test_unique_min_window(self):
        hourly = [5] * 24
        for h in range(3, 9):  # hours 3..8 empty → unique 6h min window
            hourly[h] = 0
        assert _sleep_window_start(hourly, 6) == 3

    def test_ties_resolve_to_earliest(self):
        hourly = [0] * 24  # every window ties at 0 → earliest start wins
        assert _sleep_window_start(hourly, 6) == 0


# ---------------------------------------------------------------------------
# timezone: infer_timezone
# ---------------------------------------------------------------------------


class TestInferTimezone:
    def test_below_min_samples_no_offset(self):
        est = infer_timezone(["2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z"])
        assert isinstance(est, TimezoneEstimate)
        assert est.sample_size == 2
        assert est.utc_offset is None
        assert est.peak_hour_utc is None
        assert est.quiet_hours_utc == []

    def test_buckets_and_peak(self):
        stamps = [
            "2024-01-01T14:00:00Z",
            "2024-01-01T14:30:00Z",
            "2024-01-01T15:00:00Z",
            "2024-01-01T20:00:00Z",
        ]
        est = infer_timezone(stamps)
        assert est.sample_size == 4
        assert est.hourly_utc[14] == 2
        assert est.hourly_utc[15] == 1
        assert est.peak_hour_utc == 14
        assert isinstance(est.utc_offset, int)

    def test_deterministic_offset(self):
        # Tweets in every hour except 3..8 (the unique sleep window). Centre 6 →
        # offset round(3.5 - 6) = -2.
        stamps = [
            f"2024-01-01T{h:02d}:30:00.000Z" for h in range(24) if h not in range(3, 9)
        ]
        est = infer_timezone(stamps)
        assert est.sample_size == 18
        assert est.quiet_hours_utc == [3, 4, 5, 6, 7, 8]
        assert est.utc_offset == -2

    def test_unparseable_skipped(self):
        est = infer_timezone([None, "bad", "2024-01-01T09:00:00Z"])
        assert est.sample_size == 1

    def test_to_dict_roundtrip(self):
        est = infer_timezone(["2024-01-01T09:00:00Z"])
        d = est.to_dict()
        assert set(d) == {
            "sample_size",
            "hourly_utc",
            "peak_hour_utc",
            "quiet_hours_utc",
            "utc_offset",
        }
        assert len(d["hourly_utc"]) == 24


# ---------------------------------------------------------------------------
# hashtags: _hashtags_of
# ---------------------------------------------------------------------------


class TestHashtagsOf:
    def test_list_of_dicts(self):
        raw = {"hashtags": [{"tag": "BTC", "count": 3}, {"tag": "eth", "count": 1}]}
        assert _hashtags_of(raw) == {"btc": 3, "eth": 1}

    def test_dict_form(self):
        raw = {"hashtags": {"Web3": 2}}
        assert _hashtags_of(raw) == {"web3": 2}

    def test_list_of_strings(self):
        raw = {"hashtags": ["a", "a", "b"]}
        assert _hashtags_of(raw) == {"a": 2, "b": 1}

    def test_none(self):
        assert _hashtags_of(None) == {}

    def test_missing_key(self):
        assert _hashtags_of({"other": 1}) == {}


# ---------------------------------------------------------------------------
# hashtags: tags_by_account / top_hashtags / cooccurrence
# ---------------------------------------------------------------------------


def _acct(username, tags):
    return SimpleNamespace(
        username=username,
        raw_data={"hashtags": [{"tag": t, "count": c} for t, c in tags.items()]},
    )


class TestTagsByAccount:
    def test_extracts_and_skips_tagless(self):
        accts = [
            _acct("alice", {"btc": 2, "eth": 1}),
            SimpleNamespace(username="bob", raw_data={}),  # no tags → skipped
        ]
        out = tags_by_account(accts)
        assert out == {"alice": {"btc": 2, "eth": 1}}


class TestTopHashtags:
    def test_global_ranking(self):
        tag_map = {
            "alice": {"btc": 5, "eth": 1},
            "bob": {"btc": 2, "doge": 4},
        }
        tops = top_hashtags(tag_map, limit=2)
        assert tops[0] == ("btc", 7)
        assert len(tops) == 2


class TestCooccurrence:
    def test_finds_shared(self):
        tag_map = {
            "alice": {"btc": 1, "eth": 1},
            "bob": {"btc": 1, "doge": 1},
        }
        pairs = cooccurrence(tag_map, min_shared=1)
        assert len(pairs) == 1
        p = pairs[0]
        assert isinstance(p, HashtagPair)
        assert {p.source, p.target} == {"alice", "bob"}
        assert p.shared == ["btc"]
        assert p.weight == 1

    def test_min_shared_filter(self):
        tag_map = {
            "alice": {"btc": 1, "eth": 1},
            "bob": {"btc": 1},
        }
        assert cooccurrence(tag_map, min_shared=2) == []

    def test_sorted_by_weight_desc(self):
        tag_map = {
            "a": {"x": 1, "y": 1, "z": 1},
            "b": {"x": 1, "y": 1, "z": 1},  # shares 3 with a
            "c": {"x": 1},                   # shares 1 with a and b
        }
        pairs = cooccurrence(tag_map, min_shared=1)
        assert pairs[0].weight == 3
        assert {pairs[0].source, pairs[0].target} == {"a", "b"}

    def test_empty_map(self):
        assert cooccurrence({}, min_shared=1) == []


# ---------------------------------------------------------------------------
# intersection: compute_intersection
# ---------------------------------------------------------------------------

def _net(seed_handle: str, node_handles: list[str], following: list[str]) -> dict:
    """Build a minimal subgraph dict for testing."""
    seed_id = f"twitter:{seed_handle}"
    nodes = [{"node_id": seed_id, "labels": ["Account"], "props": {}}] + [
        {"node_id": f"twitter:{h}", "labels": ["Account"], "props": {}}
        for h in node_handles
    ]
    edges = [
        {"src": seed_id, "dst": f"twitter:{h}", "rel_type": "FOLLOWS", "props": {}}
        for h in following
    ]
    return {"nodes": nodes, "edges": edges}


class TestComputeIntersection:
    def test_common_nodes_found(self):
        net_a = _net("alice", ["carol", "dave", "eve"], following=["carol", "dave"])
        net_b = _net("bob", ["carol", "frank", "eve"], following=["carol"])
        result = compute_intersection(["alice", "bob"], [net_a, net_b])
        common_handles = {n.handle for n in result.common_nodes}
        assert "carol" in common_handles
        assert "eve" in common_handles
        assert "dave" not in common_handles  # only in alice's network
        assert "frank" not in common_handles

    def test_seeds_excluded_from_common(self):
        # alice and bob appear as nodes in each other's networks
        net_a = _net("alice", ["bob", "carol"], following=[])
        net_b = _net("bob", ["alice", "carol"], following=[])
        result = compute_intersection(["alice", "bob"], [net_a, net_b])
        handles = {n.handle for n in result.common_nodes}
        assert "alice" not in handles
        assert "bob" not in handles
        assert "carol" in handles

    def test_pairwise_jaccard(self):
        # alice: {carol, dave}, bob: {carol, eve}
        # intersection={carol}, union={carol,dave,eve} → jaccard=1/3
        net_a = _net("alice", ["carol", "dave"], following=["carol"])
        net_b = _net("bob", ["carol", "eve"], following=["carol"])
        result = compute_intersection(["alice", "bob"], [net_a, net_b])
        assert len(result.pairwise) == 1
        p = result.pairwise[0]
        assert p.jaccard == round(1 / 3, 4)
        assert p.common_count == 1
        assert p.union_count == 3
        assert p.common_followings == 1

    def test_no_overlap(self):
        net_a = _net("alice", ["x", "y"], following=[])
        net_b = _net("bob", ["p", "q"], following=[])
        result = compute_intersection(["alice", "bob"], [net_a, net_b])
        assert result.common_nodes == []
        assert result.pairwise[0].jaccard == 0.0

    def test_three_seeds(self):
        net_a = _net("a", ["shared", "only_a"], following=[])
        net_b = _net("b", ["shared", "only_b"], following=[])
        net_c = _net("c", ["shared", "only_c"], following=[])
        result = compute_intersection(["a", "b", "c"], [net_a, net_b, net_c])
        shared = next(n for n in result.common_nodes if n.handle == "shared")
        assert set(shared.in_seeds) == {"a", "b", "c"}
        assert len(result.pairwise) == 3  # C(3,2) = 3

    def test_in_seeds_sorted_most_shared_first(self):
        # "shared_all" in 3 networks, "shared_two" in 2 — shared_all should rank first
        net_a = _net("a", ["shared_all", "shared_two"], following=[])
        net_b = _net("b", ["shared_all", "shared_two"], following=[])
        net_c = _net("c", ["shared_all"], following=[])
        result = compute_intersection(["a", "b", "c"], [net_a, net_b, net_c])
        assert result.common_nodes[0].handle == "shared_all"


class TestCombinedGraph:
    def test_only_keep_seeds_and_common(self):
        net_a = _net("alice", ["carol", "dave"], following=[])
        net_b = _net("bob", ["carol", "eve"], following=[])
        common_ids = {"twitter:carol"}
        nodes, edges = combined_graph(["alice", "bob"], [net_a, net_b], common_ids)
        node_ids = {n["node_id"] for n in nodes}
        assert "twitter:alice" in node_ids
        assert "twitter:bob" in node_ids
        assert "twitter:carol" in node_ids
        assert "twitter:dave" not in node_ids
        assert "twitter:eve" not in node_ids

    def test_membership_prop_set(self):
        net_a = _net("alice", ["carol"], following=["carol"])
        net_b = _net("bob", ["carol"], following=[])
        common_ids = {"twitter:carol"}
        nodes, _ = combined_graph(["alice", "bob"], [net_a, net_b], common_ids)
        carol = next(n for n in nodes if n["node_id"] == "twitter:carol")
        assert set(carol["props"]["membership"]) == {"alice", "bob"}
        assert carol["props"]["is_seed"] is False

    def test_seed_is_seed_prop(self):
        net_a = _net("alice", ["carol"], following=[])
        net_b = _net("bob", ["carol"], following=[])
        common_ids = {"twitter:carol"}
        nodes, _ = combined_graph(["alice", "bob"], [net_a, net_b], common_ids)
        alice = next(n for n in nodes if n["node_id"] == "twitter:alice")
        assert alice["props"]["is_seed"] is True

    def test_edges_deduped(self):
        # Both networks have alice→carol FOLLOWS; should appear once
        net_a = _net("alice", ["carol"], following=["carol"])
        net_b = _net("bob", ["carol"], following=[])
        # add alice→carol edge manually to net_b too
        net_b["edges"].append(
            {"src": "twitter:alice", "dst": "twitter:carol", "rel_type": "FOLLOWS", "props": {}}
        )
        common_ids = {"twitter:carol"}
        _, edges = combined_graph(["alice", "bob"], [net_a, net_b], common_ids)
        alice_carol = [e for e in edges if e["src"] == "twitter:alice" and e["dst"] == "twitter:carol"]
        assert len(alice_carol) == 1


# ---------------------------------------------------------------------------
# geo: normalize_location
# ---------------------------------------------------------------------------


class TestNormalizeLocation:
    def test_basic_lowercased(self):
        assert normalize_location("San Francisco, CA") == "san francisco, ca"

    def test_strips_emoji_and_symbols(self):
        assert normalize_location("London 🇬🇧✨") == "london"

    def test_collapses_whitespace(self):
        assert normalize_location("  New   York  ") == "new york"

    def test_none_and_empty(self):
        assert normalize_location(None) is None
        assert normalize_location("") is None
        assert normalize_location("   ") is None

    def test_junk_tokens_rejected(self):
        assert normalize_location("she/her") is None
        assert normalize_location("Planet Earth") is None
        assert normalize_location("everywhere") is None

    def test_no_letters_rejected(self):
        assert normalize_location("12345") is None
        assert normalize_location("•••") is None

    def test_single_char_rejected(self):
        assert normalize_location("x") is None

    def test_keeps_real_place_with_emoji_prefix(self):
        assert normalize_location("🌉 SF Bay Area") == "sf bay area"


# ---------------------------------------------------------------------------
# geo: tz_offset_to_lon
# ---------------------------------------------------------------------------


class TestTzOffsetToLon:
    def test_none(self):
        assert tz_offset_to_lon(None) is None

    def test_zero(self):
        assert tz_offset_to_lon(0) == 0.0

    def test_positive(self):
        assert tz_offset_to_lon(5) == 75.0

    def test_negative(self):
        assert tz_offset_to_lon(-8) == -120.0

    def test_clamped(self):
        assert tz_offset_to_lon(20) == 180.0
        assert tz_offset_to_lon(-20) == -180.0
