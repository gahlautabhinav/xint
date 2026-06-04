from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RateProfile:
    name: str
    requests_per_minute: float
    burst_capacity: float        # token bucket capacity
    human_delay_min_ms: int
    human_delay_max_ms: int
    backoff_base_s: float
    backoff_max_s: float


PROFILES: dict[str, RateProfile] = {
    "conservative": RateProfile(
        name="conservative",
        requests_per_minute=6.0,
        burst_capacity=2.0,
        human_delay_min_ms=4000,
        human_delay_max_ms=10000,
        backoff_base_s=2.0,
        backoff_max_s=120.0,
    ),
    "moderate": RateProfile(
        name="moderate",
        requests_per_minute=15.0,
        burst_capacity=5.0,
        human_delay_min_ms=2000,
        human_delay_max_ms=8000,
        backoff_base_s=1.0,
        backoff_max_s=60.0,
    ),
    "aggressive": RateProfile(
        name="aggressive",
        requests_per_minute=30.0,
        burst_capacity=10.0,
        human_delay_min_ms=500,
        human_delay_max_ms=3000,
        backoff_base_s=0.5,
        backoff_max_s=30.0,
    ),
}

ProfileName = Literal["conservative", "moderate", "aggressive"]


def get_profile(name: str) -> RateProfile:
    if name not in PROFILES:
        raise KeyError(f"Unknown rate profile: {name!r}. Valid: {list(PROFILES)}")
    return PROFILES[name]
