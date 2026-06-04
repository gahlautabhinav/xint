from __future__ import annotations

import random


def full_jitter(
    attempt: int,
    base: float = 1.0,
    max_wait: float = 60.0,
) -> float:
    """Full-jitter exponential backoff.

    Returns a random float in [0, min(max_wait, base * 2**attempt)].
    Never raises; handles attempt=0 (returns 0).

    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    """
    attempt = max(0, attempt)
    cap = min(max_wait, base * (2 ** attempt))
    return random.uniform(0.0, cap)
