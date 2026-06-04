from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class TokenBucket:
    """Async-safe per-domain token bucket rate limiter.

    Tokens refill at *rate* tokens/second up to *capacity*.
    ``acquire(n)`` blocks until *n* tokens are available.

    Uses ``asyncio.Lock`` for mutual exclusion and ``time.monotonic`` for the
    clock so tests can replace ``time.monotonic`` to simulate passage of time
    without real sleeps.
    """

    def __init__(
        self,
        capacity: float,
        rate: float,
        *,
        _clock: Callable[[], float] | None = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self._capacity = capacity
        self._rate = rate
        self._tokens = float(capacity)
        self._clock = _clock or time.monotonic
        self._last_refill = self._clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self, n: float = 1.0) -> None:
        """Block until *n* tokens are available, then consume them.

        The lock is released before sleeping so other coroutines can proceed
        concurrently — each wakes, re-acquires the lock, and re-checks the
        refilled token count.
        """
        if n > self._capacity:
            raise ValueError(f"n={n} exceeds bucket capacity={self._capacity}")
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = n - self._tokens
                wait = deficit / self._rate
            # Sleep outside the lock so other callers can make progress.
            await asyncio.sleep(wait)

    @property
    def tokens(self) -> float:
        """Current token level (approximate — not locked)."""
        return self._tokens
