from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from .models import Proxy

logger = logging.getLogger(__name__)

TEST_URLS = [
    "http://httpbin.org/ip",
    "http://ip-api.com/json",
]

_DEFAULT_TIMEOUT = 8.0


async def check(proxy: Proxy, timeout: float = _DEFAULT_TIMEOUT) -> Proxy:
    """Probe *proxy* against TEST_URLS. Mutates proxy.health in-place and returns proxy."""
    for url in TEST_URLS:
        try:
            start = time.monotonic()
            async with httpx.AsyncClient(
                proxy=proxy.url,
                timeout=timeout,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            elapsed_ms = (time.monotonic() - start) * 1000
            proxy.health.is_alive = True
            proxy.health.latency_ms = elapsed_ms
            proxy.health.last_checked_at = datetime.now(tz=timezone.utc)
            # Weighted rolling success rate (α=0.3)
            proxy.health.success_rate = 0.7 * proxy.health.success_rate + 0.3
            return proxy
        except Exception:
            continue
    # All test URLs failed
    proxy.health.is_alive = False
    proxy.health.latency_ms = None
    proxy.health.last_checked_at = datetime.now(tz=timezone.utc)
    proxy.health.success_rate = max(0.0, 0.7 * proxy.health.success_rate)
    return proxy


async def check_all(
    proxies: list[Proxy],
    timeout: float = _DEFAULT_TIMEOUT,
    concurrency: int = 20,
) -> list[Proxy]:
    """Check all proxies concurrently (bounded by *concurrency*). Returns same list."""
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(p: Proxy) -> Proxy:
        async with sem:
            return await check(p, timeout=timeout)

    results = await asyncio.gather(*(_bounded(p) for p in proxies))
    return list(results)


def filter_alive(proxies: list[Proxy]) -> list[Proxy]:
    return [p for p in proxies if p.health.is_alive]
