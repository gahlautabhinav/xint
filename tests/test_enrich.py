from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from scraper.enrich.identity import (
    IdentityHit,
    github_identity,
    gitlab_identity,
    keybase_identity,
    resolve_identity,
)
from scraper.enrich.pivots import (
    PivotLink,
    build_pivots,
    gravatar_url,
    upscale_avatar,
)
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


# ---------------------------------------------------------------------------
# pivots
# ---------------------------------------------------------------------------


class TestUpscaleAvatar:
    def test_swaps_normal_for_large(self):
        assert (
            upscale_avatar("https://pbs.twimg.com/profile_images/1/abc_normal.jpg")
            == "https://pbs.twimg.com/profile_images/1/abc_400x400.jpg"
        )

    def test_none_passthrough(self):
        assert upscale_avatar(None) is None

    def test_non_twitter_unchanged(self):
        assert upscale_avatar("https://x.test/pic.png") == "https://x.test/pic.png"


class TestGravatar:
    def test_known_hash(self):
        # The canonical Gravatar example hash for test@example.com.
        assert gravatar_url("test@example.com") == (
            "https://www.gravatar.com/55502f40dc8b7c769880b10874abc9d0"
        )

    def test_normalises_case_and_whitespace(self):
        assert gravatar_url("  Test@Example.com ") == gravatar_url("test@example.com")


def _acct(**kw):
    base = dict(
        username="alice",
        display_name="Alice A",
        website="alice.dev",
        profile_image_url="https://pbs.twimg.com/profile_images/1/a_normal.jpg",
        raw_data={"emails": ["alice@example.com"]},
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestBuildPivots:
    def test_groups_present(self):
        links = build_pivots(_acct())
        groups = {pl.group for pl in links}
        assert {"reverse_image", "identity", "dork", "breach"} <= groups
        assert all(isinstance(pl, PivotLink) for pl in links)

    def test_reverse_image_uses_upscaled_url(self):
        links = build_pivots(_acct())
        ri = [pl for pl in links if pl.group == "reverse_image"]
        assert len(ri) == 4
        assert all("_400x400" in pl.url for pl in ri)

    def test_no_image_means_no_reverse_links(self):
        links = build_pivots(_acct(profile_image_url=None))
        assert not any(pl.group == "reverse_image" for pl in links)

    def test_breach_and_gravatar_per_email(self):
        links = build_pivots(_acct(raw_data={"emails": ["a@x.com", "b@y.com"]}))
        breach = [pl for pl in links if pl.group == "breach"]
        # 2 per email (Dehashed, IntelX) + 1 HIBP page
        assert len(breach) == 5
        gravatars = [pl for pl in links if pl.label.startswith("Gravatar")]
        assert len(gravatars) == 2

    def test_no_emails_no_breach(self):
        links = build_pivots(_acct(raw_data={}))
        assert not any(pl.group == "breach" for pl in links)
        # still has wayback + handle dork
        assert any("web.archive.org" in pl.url for pl in links)


# ---------------------------------------------------------------------------
# identity (public APIs)
# ---------------------------------------------------------------------------


def _resp(status: int, payload: object):
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=payload)
    return r


def _client_returning(resp):
    c = MagicMock()
    c.get = AsyncMock(return_value=resp)
    return c


class TestGithubIdentity:
    async def test_parses_real_name_and_links(self):
        payload = {
            "name": "Linus Torvalds",
            "company": "Linux Foundation",
            "location": "Portland, OR",
            "bio": None,
            "email": None,
            "blog": "kernel.org",
            "twitter_username": "linus__t",
            "html_url": "https://github.com/torvalds",
            "followers": 200000,
            "public_repos": 7,
            "created_at": "2011-09-03T15:26:22Z",
        }
        hit = await github_identity(_client_returning(_resp(200, payload)), "torvalds")
        assert hit is not None
        assert hit.real_name == "Linus Torvalds"
        assert hit.company == "Linux Foundation"
        services = {la.service for la in hit.linked_accounts}
        assert services == {"twitter", "website"}
        assert hit.extra["followers"] == 200000

    async def test_404_returns_none(self):
        hit = await github_identity(_client_returning(_resp(404, {})), "nobody")
        assert hit is None


class TestGitlabIdentity:
    async def test_parses_first_match(self):
        payload = [
            {
                "id": 5,
                "name": "Jane Doe",
                "web_url": "https://gitlab.com/jane",
                "bio": "dev",
                "location": "Berlin",
                "organization": "Acme",
                "state": "active",
            }
        ]
        hit = await gitlab_identity(_client_returning(_resp(200, payload)), "jane")
        assert hit is not None
        assert hit.real_name == "Jane Doe"
        assert hit.location == "Berlin"
        assert hit.company == "Acme"

    async def test_empty_array_none(self):
        hit = await gitlab_identity(_client_returning(_resp(200, [])), "nobody")
        assert hit is None


class TestKeybaseIdentity:
    async def test_parses_proofs(self):
        payload = {
            "status": {"code": 0},
            "them": [
                {
                    "basics": {"username": "chris"},
                    "profile": {"full_name": "Chris Coyne", "location": "NYC"},
                    "proofs_summary": {
                        "all": [
                            {"proof_type": "twitter", "nametag": "malg", "service_url": "https://twitter.com/malg"},
                            {"proof_type": "github", "nametag": "chris", "service_url": "https://github.com/chris"},
                        ]
                    },
                }
            ],
        }
        hit = await keybase_identity(_client_returning(_resp(200, payload)), "chris")
        assert hit is not None
        assert hit.real_name == "Chris Coyne"
        assert hit.url == "https://keybase.io/chris"
        services = {la.service for la in hit.linked_accounts}
        assert services == {"twitter", "github"}

    async def test_null_them_none(self):
        hit = await keybase_identity(_client_returning(_resp(200, {"them": [None]})), "nobody")
        assert hit is None


class TestResolveIdentity:
    async def test_gathers_and_drops_none(self):
        gh = IdentityHit(source="github", real_name="A")
        kb = IdentityHit(source="keybase", real_name="B")
        with (
            patch("scraper.enrich.identity.github_identity", AsyncMock(return_value=gh)),
            patch("scraper.enrich.identity.gitlab_identity", AsyncMock(return_value=None)),
            patch("scraper.enrich.identity.keybase_identity", AsyncMock(return_value=kb)),
        ):
            hits = await resolve_identity("x")
        assert {h.source for h in hits} == {"github", "keybase"}
