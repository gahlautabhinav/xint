from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from scraper.enrich.sites import SITES, Site
from scraper.enrich.username_enum import (
    SiteResult,
    detect,
    enumerate_username,
    is_valid_username,
)

# ---------------------------------------------------------------------------
# is_valid_username
# ---------------------------------------------------------------------------


class TestIsValidUsername:
    def test_plain_handle(self):
        assert is_valid_username("elonmusk")

    def test_with_allowed_separators(self):
        assert is_valid_username("john_doe.99-x")

    def test_rejects_slash(self):
        assert not is_valid_username("foo/bar")

    def test_rejects_path_traversal(self):
        assert not is_valid_username("../admin")

    def test_rejects_query_chars(self):
        assert not is_valid_username("foo?x=1")
        assert not is_valid_username("foo bar")

    def test_rejects_empty(self):
        assert not is_valid_username("")

    def test_rejects_too_long(self):
        assert not is_valid_username("a" * 41)


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

_STATUS = Site("S", "code", "https://s/{username}")
_ABSENT = Site("A", "code", "https://a/{username}", check="absent", marker="No such user.")
_PRESENT = Site("P", "code", "https://p/{username}", check="present", marker="profile")


class TestDetect:
    def test_status_200_found(self):
        assert detect(_STATUS, 200, "") == "found"

    def test_status_404_not_found(self):
        assert detect(_STATUS, 404, "") == "not_found"

    def test_status_403_unknown(self):
        assert detect(_STATUS, 403, "") == "unknown"

    def test_status_429_unknown(self):
        assert detect(_STATUS, 429, "") == "unknown"

    def test_absent_marker_present_means_not_found(self):
        assert detect(_ABSENT, 200, "No such user.") == "not_found"

    def test_absent_marker_missing_means_found(self):
        assert detect(_ABSENT, 200, "<h1>real profile</h1>") == "found"

    def test_present_marker_found(self):
        assert detect(_PRESENT, 200, "this is a profile page") == "found"

    def test_present_marker_missing(self):
        assert detect(_PRESENT, 200, "nothing here") == "not_found"

    def test_marker_check_404_is_not_found(self):
        assert detect(_ABSENT, 404, "") == "not_found"

    def test_marker_check_500_unknown(self):
        assert detect(_ABSENT, 500, "") == "unknown"


# ---------------------------------------------------------------------------
# site registry sanity
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_sites_have_username_placeholder(self):
        for s in SITES:
            assert "{username}" in s.url, s.name

    def test_marker_sites_have_marker(self):
        for s in SITES:
            if s.check in ("absent", "present"):
                assert s.marker, s.name

    def test_unique_names(self):
        names = [s.name for s in SITES]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# enumerate_username (mocked HTTP)
# ---------------------------------------------------------------------------


def _fake_client(status_by_host: dict[str, int]):
    """An httpx.AsyncClient stand-in whose .get returns a status by URL host."""

    async def _get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = next(
            (code for host, code in status_by_host.items() if host in url), 404
        )
        resp.text = ""
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=_get)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestEnumerateUsername:
    async def test_classifies_found_and_not_found(self):
        sites = [
            Site("GitHub", "code", "https://github.com/{username}"),
            Site("GitLab", "code", "https://gitlab.com/{username}"),
        ]
        cm = _fake_client({"github.com": 200, "gitlab.com": 404})
        with patch("scraper.enrich.username_enum.httpx.AsyncClient", return_value=cm):
            results = await enumerate_username("alice", sites=sites)

        by_name = {r.name: r.status for r in results}
        assert by_name == {"GitHub": "found", "GitLab": "not_found"}
        assert all(isinstance(r, SiteResult) for r in results)

    async def test_network_error_is_unknown(self):
        sites = [Site("GitHub", "code", "https://github.com/{username}")]
        import httpx

        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        with patch("scraper.enrich.username_enum.httpx.AsyncClient", return_value=cm):
            results = await enumerate_username("alice", sites=sites)

        assert results[0].status == "unknown"
