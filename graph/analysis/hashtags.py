"""Hashtag aggregation and co-occurrence analysis across accounts.

Two accounts that lean on the same hashtags (#bitcoin, #maga, a niche event tag)
are often part of the same community even with no direct follow/mention edge. This
module turns the per-account hashtag tallies stored in ``Account.raw_data["hashtags"]``
into (a) a global hashtag ranking and (b) a list of account pairs that share tags —
a lightweight "interest graph" overlay on top of the relationship graph.

Pure functions operate on a normalised ``{username: {tag: count}}`` map so they're
trivially unit-testable; :func:`tags_by_account` adapts ORM rows into that shape.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

__all__ = [
    "HashtagPair",
    "tags_by_account",
    "top_hashtags",
    "cooccurrence",
]


@dataclass
class HashtagPair:
    """Two accounts that share one or more hashtags."""

    source: str
    target: str
    shared: list[str]          # the overlapping tags (sorted)
    weight: int                # number of shared tags

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "shared": self.shared,
            "weight": self.weight,
        }


def _hashtags_of(raw_data: Any) -> dict[str, int]:
    """Pull a ``{tag: count}`` map out of an Account.raw_data blob.

    Accepts both the stored list form ``[{"tag": "x", "count": 3}, ...]`` and a
    plain ``{tag: count}`` dict. Returns ``{}`` for anything else.
    """
    if not isinstance(raw_data, dict):
        return {}
    tags = raw_data.get("hashtags")
    if isinstance(tags, dict):
        return {str(k).lower(): int(v) for k, v in tags.items()}
    if isinstance(tags, list):
        out: dict[str, int] = {}
        for item in tags:
            if isinstance(item, dict) and "tag" in item:
                out[str(item["tag"]).lower()] = int(item.get("count", 1))
            elif isinstance(item, str):
                out[item.lower()] = out.get(item.lower(), 0) + 1
        return out
    return {}


def tags_by_account(accounts: list[Any]) -> dict[str, dict[str, int]]:
    """Adapt ORM Account rows → ``{username: {tag: count}}`` (skips tagless accounts)."""
    result: dict[str, dict[str, int]] = {}
    for acct in accounts:
        tags = _hashtags_of(getattr(acct, "raw_data", None))
        if tags:
            result[getattr(acct, "username", "")] = tags
    return result


def top_hashtags(
    tag_map: dict[str, dict[str, int]],
    limit: int = 25,
) -> list[tuple[str, int]]:
    """Global hashtag ranking: ``[(tag, total_count), ...]`` descending."""
    totals: Counter[str] = Counter()
    for tags in tag_map.values():
        for tag, count in tags.items():
            totals[tag.lower()] += count
    return totals.most_common(limit)


def cooccurrence(
    tag_map: dict[str, dict[str, int]],
    min_shared: int = 1,
    limit: int = 200,
) -> list[HashtagPair]:
    """Find account pairs sharing >= *min_shared* hashtags.

    Returns pairs sorted by overlap size (descending), capped at *limit*.
    O(n^2) over accounts — fine for the hundreds-of-nodes graphs this tool builds.
    """
    usernames = list(tag_map.keys())
    pairs: list[HashtagPair] = []
    for i in range(len(usernames)):
        a = usernames[i]
        tags_a = set(tag_map[a])
        for j in range(i + 1, len(usernames)):
            b = usernames[j]
            shared = tags_a & set(tag_map[b])
            if len(shared) >= min_shared:
                pairs.append(
                    HashtagPair(
                        source=a,
                        target=b,
                        shared=sorted(shared),
                        weight=len(shared),
                    )
                )
    pairs.sort(key=lambda p: p.weight, reverse=True)
    return pairs[:limit]
