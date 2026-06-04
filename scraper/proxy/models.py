from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProxyHealth:
    latency_ms: float | None = None
    success_rate: float = 1.0  # 0.0–1.0
    last_checked_at: datetime | None = None
    is_alive: bool = True


@dataclass
class Proxy:
    host: str
    port: int
    scheme: str = "http"  # http | https | socks5
    username: str | None = None
    password: str | None = None
    health: ProxyHealth = field(default_factory=ProxyHealth)

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    def __hash__(self) -> int:
        return hash((self.scheme, self.host, self.port, self.username, self.password))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Proxy):
            return NotImplemented
        return (
            self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
            and self.username == other.username
            and self.password == other.password
        )
