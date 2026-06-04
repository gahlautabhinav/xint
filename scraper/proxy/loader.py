from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from .models import Proxy

logger = logging.getLogger(__name__)

# Supported line formats (all after stripping comments / blank lines):
#   host:port
#   scheme://host:port
#   scheme://user:pass@host:port
#   user:pass@host:port  (scheme defaults to http)
_FULL_RE = re.compile(
    r"^(?:(?P<scheme>https?|socks5)://)?(?:(?P<user>[^:@]+):(?P<password>[^@]+)@)?(?P<host>[^:]+):(?P<port>\d+)$"
)

PROXYSCRAPE_URL = (
    "https://api.proxyscrape.com/v2/"
    "?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all"
)


def _parse_line(line: str) -> Proxy | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = _FULL_RE.match(line)
    if not m:
        logger.debug("Skipping malformed proxy line: %r", line)
        return None
    return Proxy(
        host=m.group("host").strip(),
        port=int(m.group("port")),
        scheme=m.group("scheme") or "http",
        username=m.group("user"),
        password=m.group("password"),
    )


def load_from_file(path: str) -> list[Proxy]:
    """Load proxies from *path*. Skips blank lines, comments, malformed entries."""
    p = Path(path)
    if not p.exists():
        logger.warning("Proxy file not found: %s", path)
        return []
    proxies: list[Proxy] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        proxy = _parse_line(line)
        if proxy is not None:
            proxies.append(proxy)
    logger.info("Loaded %d proxies from %s", len(proxies), path)
    return proxies


async def fetch_free_proxies(url: str = PROXYSCRAPE_URL, timeout: float = 10.0) -> list[Proxy]:
    """Fetch free proxy list from proxyscrape.com. Returns empty list on failure."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("fetch_free_proxies failed: %s", exc)
        return []
    proxies: list[Proxy] = []
    for line in resp.text.splitlines():
        proxy = _parse_line(line)
        if proxy is not None:
            proxies.append(proxy)
    logger.info("Fetched %d free proxies", len(proxies))
    return proxies


def get_all(file_path: str, fetched: list[Proxy] | None = None) -> list[Proxy]:
    """Merge file-loaded proxies with pre-fetched ones. Deduplicates by (scheme, host, port, user)."""
    from_file = load_from_file(file_path)
    combined = list(from_file)
    if fetched:
        seen = set(combined)
        for p in fetched:
            if p not in seen:
                combined.append(p)
                seen.add(p)
    return combined
