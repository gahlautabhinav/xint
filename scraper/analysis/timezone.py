"""Infer an account's likely timezone from its tweet timestamps.

Twitter never exposes a user's timezone, but posting activity is a strong proxy:
people are least active while asleep (~03:30 local). We bucket every tweet by its
UTC hour, find the lowest-activity contiguous window (the inferred sleep window),
and assume its centre lands near local 03:30 — which yields a UTC offset estimate.

This is a heuristic OSINT signal (the same trick `tweets_analyzer` / `sleepytime`
use), not a precise lookup: noisy timelines, scheduled posts, and globe-trotting
users degrade it. ``utc_offset`` is ``None`` until enough samples accumulate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

__all__ = ["TimezoneEstimate", "infer_timezone"]

# Need a few timestamps before an offset guess is meaningful.
_MIN_SAMPLES = 4
# Length of the assumed sleep window, in hours.
_SLEEP_WINDOW = 6
# Local clock time we assume the centre of the sleep window maps to (03:30).
_SLEEP_CENTRE_LOCAL = 3.5


@dataclass
class TimezoneEstimate:
    """Result of timezone inference over a set of tweet timestamps."""

    sample_size: int
    hourly_utc: list[int]              # 24 buckets: tweet count per UTC hour
    peak_hour_utc: int | None = None   # busiest UTC hour
    quiet_hours_utc: list[int] = None  # type: ignore[assignment]  # inferred sleep window (UTC hours)
    utc_offset: int | None = None      # estimated offset, e.g. -5, +1

    def __post_init__(self) -> None:
        if self.quiet_hours_utc is None:
            self.quiet_hours_utc = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "hourly_utc": self.hourly_utc,
            "peak_hour_utc": self.peak_hour_utc,
            "quiet_hours_utc": self.quiet_hours_utc,
            "utc_offset": self.utc_offset,
        }


def _parse_hour_utc(ts: str | None) -> int | None:
    """Return the UTC hour (0-23) of an ISO-8601 timestamp, or None if unparseable.

    Twitter stamps are UTC with a trailing ``Z`` (e.g. ``2024-01-01T10:00:00.000Z``).
    Python 3.10's ``fromisoformat`` rejects ``Z`` and accepts only 3/6-digit
    fractions, so we normalise the ``Z`` first.
    """
    if not ts:
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.hour


def _sleep_window_start(hourly: list[int], width: int = _SLEEP_WINDOW) -> int:
    """Return the start hour of the lowest-activity contiguous (circular) window.

    Ties resolve to the earliest start hour (deterministic).
    """
    best_start = 0
    best_sum = None
    for start in range(24):
        total = sum(hourly[(start + i) % 24] for i in range(width))
        if best_sum is None or total < best_sum:
            best_sum = total
            best_start = start
    return best_start


def _normalize_offset(offset: int) -> int:
    """Wrap a raw offset into the conventional (-12, +12] range."""
    return ((offset + 12) % 24) - 12


def infer_timezone(timestamps: list[str | None]) -> TimezoneEstimate:
    """Estimate posting timezone from a list of ISO-8601 tweet timestamps."""
    hourly = [0] * 24
    sample_size = 0
    for ts in timestamps:
        hour = _parse_hour_utc(ts)
        if hour is None:
            continue
        hourly[hour] += 1
        sample_size += 1

    if sample_size < _MIN_SAMPLES:
        return TimezoneEstimate(sample_size=sample_size, hourly_utc=hourly)

    peak_hour_utc = max(range(24), key=lambda h: hourly[h])
    start = _sleep_window_start(hourly, _SLEEP_WINDOW)
    quiet_hours = [(start + i) % 24 for i in range(_SLEEP_WINDOW)]
    centre_utc = start + _SLEEP_WINDOW / 2.0
    utc_offset = _normalize_offset(round(_SLEEP_CENTRE_LOCAL - centre_utc))

    return TimezoneEstimate(
        sample_size=sample_size,
        hourly_utc=hourly,
        peak_hour_utc=peak_hour_utc,
        quiet_hours_utc=quiet_hours,
        utc_offset=utc_offset,
    )
