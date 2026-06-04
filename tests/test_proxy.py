from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from scraper.proxy.loader import _parse_line, fetch_free_proxies, get_all, load_from_file
from scraper.proxy.models import Proxy
from scraper.proxy.rotator import ProxyRotator

# ---------------------------------------------------------------------------
# _parse_line — format coverage
# ---------------------------------------------------------------------------

class TestParseLineFormats:
    def test_host_port(self):
        p = _parse_line("1.2.3.4:8080")
        assert p is not None
        assert p.host == "1.2.3.4"
        assert p.port == 8080
        assert p.scheme == "http"
        assert p.username is None

    def test_scheme_host_port(self):
        p = _parse_line("socks5://5.6.7.8:1080")
        assert p is not None
        assert p.scheme == "socks5"
        assert p.host == "5.6.7.8"
        assert p.port == 1080

    def test_https_scheme(self):
        p = _parse_line("https://10.0.0.1:3128")
        assert p is not None
        assert p.scheme == "https"

    def test_user_pass_at_host_port(self):
        p = _parse_line("user:secret@192.168.1.1:9090")
        assert p is not None
        assert p.username == "user"
        assert p.password == "secret"
        assert p.host == "192.168.1.1"
        assert p.port == 9090

    def test_full_url_with_auth(self):
        p = _parse_line("http://alice:pw@proxy.example.com:8888")
        assert p is not None
        assert p.scheme == "http"
        assert p.username == "alice"
        assert p.password == "pw"
        assert p.host == "proxy.example.com"
        assert p.port == 8888

    def test_blank_line_returns_none(self):
        assert _parse_line("") is None
        assert _parse_line("   ") is None

    def test_comment_returns_none(self):
        assert _parse_line("# comment") is None

    def test_malformed_returns_none(self):
        assert _parse_line("notaproxy") is None
        assert _parse_line("host_only") is None


# ---------------------------------------------------------------------------
# load_from_file
# ---------------------------------------------------------------------------

class TestLoadFromFile:
    def test_loads_multiple_formats(self, tmp_path):
        pf = tmp_path / "proxies.txt"
        pf.write_text(
            "1.1.1.1:3128\n"
            "socks5://2.2.2.2:1080\n"
            "# skip me\n"
            "\n"
            "user:pw@3.3.3.3:8080\n",
            encoding="utf-8",
        )
        proxies = load_from_file(str(pf))
        assert len(proxies) == 3

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_from_file(str(tmp_path / "nonexistent.txt"))
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        pf = tmp_path / "empty.txt"
        pf.write_text("", encoding="utf-8")
        assert load_from_file(str(pf)) == []


# ---------------------------------------------------------------------------
# fetch_free_proxies — mocked httpx
# ---------------------------------------------------------------------------

class TestFetchFreeProxies:
    async def test_parses_response_lines(self):
        body = "1.2.3.4:8080\n5.6.7.8:3128\nbad\n"
        mock_resp = MagicMock()
        mock_resp.text = body
        mock_resp.raise_for_status = MagicMock()

        with patch("scraper.proxy.loader.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_free_proxies()

        assert len(result) == 2
        assert result[0].host == "1.2.3.4"

    async def test_returns_empty_on_http_error(self):
        with patch("scraper.proxy.loader.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_free_proxies()
        assert result == []


# ---------------------------------------------------------------------------
# get_all — merge + dedup
# ---------------------------------------------------------------------------

class TestGetAll:
    def test_deduplicates(self, tmp_path):
        pf = tmp_path / "p.txt"
        pf.write_text("1.1.1.1:8080\n", encoding="utf-8")
        dup = Proxy(host="1.1.1.1", port=8080)
        extra = Proxy(host="2.2.2.2", port=9090)
        result = get_all(str(pf), fetched=[dup, extra])
        assert len(result) == 2  # dup excluded

    def test_none_fetched(self, tmp_path):
        pf = tmp_path / "p.txt"
        pf.write_text("1.1.1.1:8080\n", encoding="utf-8")
        result = get_all(str(pf), fetched=None)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# ProxyRotator
# ---------------------------------------------------------------------------

class TestProxyRotator:
    def _make_proxy(self, host: str, alive: bool = True, sr: float = 1.0, latency: float = 100.0) -> Proxy:
        p = Proxy(host=host, port=8080)
        p.health.is_alive = alive
        p.health.success_rate = sr
        p.health.latency_ms = latency
        return p

    def test_next_excludes_dead(self):
        dead = self._make_proxy("dead.host", alive=False)
        alive = self._make_proxy("alive.host", alive=True)
        rotator = ProxyRotator([dead, alive])
        for _ in range(20):
            result = rotator.next()
            assert result is not None
            assert result.host == "alive.host"

    def test_empty_pool_returns_none(self):
        rotator = ProxyRotator([])
        assert rotator.next() is None

    def test_all_dead_returns_none(self):
        dead = self._make_proxy("dead.host", alive=False)
        rotator = ProxyRotator([dead])
        assert rotator.next() is None

    def test_mark_failed_reduces_score(self):
        p = self._make_proxy("h", sr=1.0)
        rotator = ProxyRotator([p])
        rotator.mark_failed(p)
        assert p.health.success_rate < 1.0

    def test_mark_failed_kills_at_zero(self):
        p = self._make_proxy("h", sr=0.0)
        rotator = ProxyRotator([p])
        rotator.mark_failed(p)
        assert p.health.is_alive is False

    def test_mark_success_increases_score(self):
        p = self._make_proxy("h", sr=0.5)
        rotator = ProxyRotator([p])
        rotator.mark_success(p)
        assert p.health.success_rate > 0.5

    def test_mark_success_caps_at_one(self):
        p = self._make_proxy("h", sr=1.0)
        rotator = ProxyRotator([p])
        rotator.mark_success(p)
        assert p.health.success_rate <= 1.0

    def test_add_deduplicates(self):
        p = self._make_proxy("h")
        rotator = ProxyRotator([p])
        rotator.add(p)
        assert rotator.pool_size() == 1

    def test_pool_size_counts_alive(self):
        dead = self._make_proxy("dead", alive=False)
        alive = self._make_proxy("alive", alive=True)
        rotator = ProxyRotator([dead, alive])
        assert rotator.pool_size() == 1
