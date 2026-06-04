from __future__ import annotations

import asyncio
import random

import pytest

from scraper.ratelimit.backoff import full_jitter
from scraper.ratelimit.profiles import PROFILES, get_profile
from scraper.ratelimit.token_bucket import TokenBucket

# ---------------------------------------------------------------------------
# full_jitter backoff
# ---------------------------------------------------------------------------

class TestFullJitter:
    def test_attempt_0_returns_zero_or_near(self):
        # base * 2**0 = base=1.0, so range is [0, 1.0]
        rng = random.Random(42)
        with _patch_random(rng):
            val = full_jitter(attempt=0, base=1.0)
        assert 0.0 <= val <= 1.0

    def test_grows_with_attempt(self):
        # With fixed seed, compare distribution caps
        vals_low = [full_jitter(attempt=1) for _ in range(50)]
        vals_high = [full_jitter(attempt=5) for _ in range(50)]
        assert max(vals_low) < max(vals_high) or max(vals_low) <= 2.0

    def test_capped_at_max_wait(self):
        for _ in range(100):
            val = full_jitter(attempt=20, base=1.0, max_wait=10.0)
            assert val <= 10.0

    def test_non_negative(self):
        for attempt in range(10):
            assert full_jitter(attempt) >= 0.0

    def test_base_affects_cap(self):
        # With very small base, cap is tiny
        val = full_jitter(attempt=3, base=0.001, max_wait=60.0)
        assert val <= 0.001 * (2 ** 3)


class _patch_random:
    """Context manager: temporarily replace random.uniform with seeded version."""
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._orig = None

    def __enter__(self):
        import scraper.ratelimit.backoff as mod
        self._mod = mod
        self._orig = random.uniform
        random.uniform = self._rng.uniform  # type: ignore[assignment]
        return self

    def __exit__(self, *_):
        random.uniform = self._orig  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# TokenBucket — fake clock, no real sleeps
# ---------------------------------------------------------------------------

class FakeClock:
    """Monotonic fake clock. Advance by calling tick(seconds)."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def tick(self, seconds: float) -> None:
        self._t += seconds


class TestTokenBucket:
    async def test_immediate_acquire_when_full(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10.0, rate=1.0, _clock=clock)
        # Full bucket — should not sleep at all
        await asyncio.wait_for(bucket.acquire(1.0), timeout=0.1)

    async def test_refill_after_time(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5.0, rate=2.0, _clock=clock)
        # Drain completely
        await asyncio.wait_for(bucket.acquire(5.0), timeout=0.1)
        assert bucket.tokens == pytest.approx(0.0, abs=1e-9)
        # Advance 2.5 seconds → 5 tokens refilled
        clock.tick(2.5)
        await asyncio.wait_for(bucket.acquire(5.0), timeout=0.1)

    async def test_tokens_capped_at_capacity(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=3.0, rate=1.0, _clock=clock)
        await asyncio.wait_for(bucket.acquire(3.0), timeout=0.1)
        clock.tick(100.0)  # Way more than capacity
        # Force a refill by acquiring
        await asyncio.wait_for(bucket.acquire(1.0), timeout=0.1)
        assert bucket.tokens <= 3.0

    async def test_partial_acquire(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10.0, rate=1.0, _clock=clock)
        await asyncio.wait_for(bucket.acquire(3.0), timeout=0.1)
        assert bucket.tokens == pytest.approx(7.0, abs=1e-9)

    def test_invalid_capacity_raises(self):
        with pytest.raises(ValueError, match="capacity"):
            TokenBucket(capacity=0.0, rate=1.0)

    def test_invalid_rate_raises(self):
        with pytest.raises(ValueError, match="rate"):
            TokenBucket(capacity=5.0, rate=0.0)

    async def test_acquire_more_than_capacity_raises(self):
        bucket = TokenBucket(capacity=5.0, rate=1.0)
        with pytest.raises(ValueError, match="capacity"):
            await bucket.acquire(6.0)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

class TestProfiles:
    @pytest.mark.parametrize("name", ["conservative", "moderate", "aggressive"])
    def test_profile_exists(self, name: str):
        p = get_profile(name)  # type: ignore[arg-type]
        assert p.name == name

    def test_conservative_slowest(self):
        c = get_profile("conservative")
        m = get_profile("moderate")
        a = get_profile("aggressive")
        assert c.requests_per_minute < m.requests_per_minute < a.requests_per_minute

    def test_conservative_longest_delay(self):
        c = get_profile("conservative")
        a = get_profile("aggressive")
        assert c.human_delay_min_ms > a.human_delay_min_ms
        assert c.human_delay_max_ms > a.human_delay_max_ms

    def test_conservative_largest_backoff(self):
        c = get_profile("conservative")
        a = get_profile("aggressive")
        assert c.backoff_max_s > a.backoff_max_s

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError):
            get_profile("turbo")  # type: ignore[arg-type]

    def test_all_profiles_positive_rate(self):
        for p in PROFILES.values():
            assert p.requests_per_minute > 0
            assert p.burst_capacity > 0

    def test_burst_capacity_gte_one(self):
        for p in PROFILES.values():
            assert p.burst_capacity >= 1.0
