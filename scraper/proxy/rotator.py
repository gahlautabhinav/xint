from __future__ import annotations

import logging
import random

from .models import Proxy

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Weighted-random proxy selection by health score.

    Weight = success_rate / max(latency_ms, 1).  Dead proxies excluded.
    Falls back to direct connection (None) when pool exhausted.
    """

    def __init__(self, proxies: list[Proxy]) -> None:
        self._proxies: list[Proxy] = list(proxies)

    def _alive(self) -> list[Proxy]:
        return [p for p in self._proxies if p.health.is_alive]

    def _weight(self, p: Proxy) -> float:
        latency = p.health.latency_ms if p.health.latency_ms is not None else 5000.0
        return p.health.success_rate / max(latency, 1.0)

    def next(self) -> Proxy | None:
        """Return a proxy (or None = direct) sampled by weight."""
        alive = self._alive()
        if not alive:
            logger.warning("ProxyRotator: pool exhausted, falling back to direct connection")
            return None
        weights = [self._weight(p) for p in alive]
        total = sum(weights)
        if total == 0:
            return random.choice(alive)
        return random.choices(alive, weights=weights, k=1)[0]

    def mark_failed(self, proxy: Proxy) -> None:
        """Penalise a proxy after a request failure."""
        proxy.health.success_rate = max(0.0, proxy.health.success_rate - 0.2)
        if proxy.health.success_rate <= 0.0:
            proxy.health.is_alive = False
            logger.debug("Proxy marked dead: %s", proxy.url)

    def mark_success(self, proxy: Proxy) -> None:
        """Reward a proxy after a successful request."""
        proxy.health.success_rate = min(1.0, proxy.health.success_rate + 0.05)
        proxy.health.is_alive = True

    def add(self, proxy: Proxy) -> None:
        if proxy not in self._proxies:
            self._proxies.append(proxy)

    def pool_size(self) -> int:
        return len(self._alive())
