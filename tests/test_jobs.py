from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from scraper.extractors.twitter import ProfileData, TweetData
from scraper.jobs.crawler import AccountCrawler, CrawlerConfig, _proxies_from_urls
from scraper.jobs.worker import ScrapeResult, scrape_account
from scraper.ratelimit.profiles import get_profile
from scraper.ratelimit.token_bucket import TokenBucket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(handle: str = "alice") -> ProfileData:
    return ProfileData(
        handle=handle,
        display_name=handle.title(),
        bio=f"bio of {handle}",
        website=None,
        follower_count=100,
        following_count=50,
        is_verified=False,
    )


def _empty_profile() -> ProfileData:
    return ProfileData(handle=None, display_name=None, bio=None, website=None)


def _make_bucket() -> TokenBucket:
    # Instant-grant bucket (capacity 100, very fast rate)
    return TokenBucket(capacity=100.0, rate=100.0)


def _moderate_profile():
    return get_profile("moderate")


# ---------------------------------------------------------------------------
# _proxies_from_urls
# ---------------------------------------------------------------------------


class TestProxiesFromUrls:
    def test_valid_http_proxy(self):
        proxies = _proxies_from_urls(["http://1.2.3.4:8080"])
        assert len(proxies) == 1
        assert proxies[0].host == "1.2.3.4"
        assert proxies[0].port == 8080
        assert proxies[0].scheme == "http"

    def test_proxy_with_auth(self):
        proxies = _proxies_from_urls(["http://user:pass@1.2.3.4:8080"])
        assert proxies[0].username == "user"
        assert proxies[0].password == "pass"

    def test_invalid_url_skipped(self):
        proxies = _proxies_from_urls(["not_a_url", "http://1.2.3.4:9090"])
        assert len(proxies) == 1
        assert proxies[0].port == 9090

    def test_empty_list(self):
        assert _proxies_from_urls([]) == []


# ---------------------------------------------------------------------------
# scrape_account
# ---------------------------------------------------------------------------


class TestScrapeAccount:
    async def test_success(self):
        page = AsyncMock()
        bucket = _make_bucket()
        profile = _make_profile("alice")
        tweets = [
            TweetData(
                tweet_id="1",
                text="Hello @bob",
                timestamp=None,
                mentions=["bob"],
            )
        ]
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.human_delay", new=AsyncMock()),
            patch("scraper.jobs.worker.scroll_page", new=AsyncMock()),
            patch("scraper.jobs.worker.extract_profile", new=AsyncMock(return_value=profile)),
            patch("scraper.jobs.worker.extract_tweets", new=AsyncMock(return_value=tweets)),
        ):
            result = await scrape_account(
                page, "alice", bucket=bucket, rate_profile=_moderate_profile()
            )

        assert result.success is True
        assert result.username == "alice"
        assert result.profile.handle == "alice"
        assert result.tweets == tweets
        assert result.error is None
        assert result.following == []  # not requested by default

    async def test_navigation_failure(self):
        page = AsyncMock()
        bucket = _make_bucket()
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=False)),
        ):
            result = await scrape_account(
                page, "alice", bucket=bucket, rate_profile=_moderate_profile()
            )

        assert result.success is False
        assert result.error == "navigation failed"

    async def test_selector_not_found(self):
        page = AsyncMock()
        bucket = _make_bucket()
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=False)),
        ):
            result = await scrape_account(
                page, "alice", bucket=bucket, rate_profile=_moderate_profile()
            )

        assert result.success is False
        assert result.error == "profile selector not found"

    async def test_exception_returns_failure(self):
        page = AsyncMock()
        bucket = _make_bucket()
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.human_delay", new=AsyncMock()),
            patch(
                "scraper.jobs.worker.extract_profile",
                new=AsyncMock(side_effect=RuntimeError("DOM exploded")),
            ),
        ):
            result = await scrape_account(
                page, "alice", bucket=bucket, rate_profile=_moderate_profile()
            )

        assert result.success is False
        assert "DOM exploded" in (result.error or "")

    async def test_bucket_acquired(self):
        page = AsyncMock()
        mock_bucket = MagicMock()
        mock_bucket.acquire = AsyncMock()
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=False)),
        ):
            await scrape_account(
                page, "alice", bucket=mock_bucket, rate_profile=_moderate_profile()
            )

        mock_bucket.acquire.assert_called_once()

    async def test_cross_platform_extracted(self):
        page = AsyncMock()
        bucket = _make_bucket()
        profile = ProfileData(
            handle="alice",
            display_name="Alice",
            bio="github.com/alice-dev",
            website=None,
        )
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.human_delay", new=AsyncMock()),
            patch("scraper.jobs.worker.scroll_page", new=AsyncMock()),
            patch("scraper.jobs.worker.extract_profile", new=AsyncMock(return_value=profile)),
            patch("scraper.jobs.worker.extract_tweets", new=AsyncMock(return_value=[])),
        ):
            result = await scrape_account(
                page, "alice", bucket=bucket, rate_profile=_moderate_profile()
            )

        assert result.success is True
        assert result.cross_platform.get("github") == "alice-dev"

    async def test_scrape_following_when_enabled(self):
        page = AsyncMock()
        bucket = _make_bucket()
        profile = _make_profile("alice")
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.human_delay", new=AsyncMock()),
            patch("scraper.jobs.worker.scroll_page", new=AsyncMock()),
            patch("scraper.jobs.worker.extract_profile", new=AsyncMock(return_value=profile)),
            patch("scraper.jobs.worker.extract_tweets", new=AsyncMock(return_value=[])),
            patch(
                "scraper.jobs.worker.extract_following",
                new=AsyncMock(return_value=["bob", "carol"]),
            ),
        ):
            result = await scrape_account(
                page,
                "alice",
                bucket=bucket,
                rate_profile=_moderate_profile(),
                scrape_following=True,
                max_following=10,
            )

        assert result.success is True
        assert result.following == ["bob", "carol"]
        assert result.followers == []  # not requested

    async def test_scrape_followers_when_enabled(self):
        page = AsyncMock()
        bucket = _make_bucket()
        profile = _make_profile("alice")
        with (
            patch("scraper.jobs.worker.safe_goto", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.wait_for_selector", new=AsyncMock(return_value=True)),
            patch("scraper.jobs.worker.human_delay", new=AsyncMock()),
            patch("scraper.jobs.worker.scroll_page", new=AsyncMock()),
            patch("scraper.jobs.worker.extract_profile", new=AsyncMock(return_value=profile)),
            patch("scraper.jobs.worker.extract_tweets", new=AsyncMock(return_value=[])),
            patch(
                "scraper.jobs.worker.extract_following",
                new=AsyncMock(return_value=["dave", "erin"]),
            ),
        ):
            result = await scrape_account(
                page,
                "alice",
                bucket=bucket,
                rate_profile=_moderate_profile(),
                scrape_followers=True,
                max_followers=10,
            )

        assert result.success is True
        assert result.followers == ["dave", "erin"]
        assert result.following == []  # not requested


# ---------------------------------------------------------------------------
# AccountCrawler helpers
# ---------------------------------------------------------------------------


def _make_mock_session_factory():
    """Return a mock session factory wired to mock repos."""
    mock_job = MagicMock()
    mock_job.id = uuid.uuid4()

    mock_account = MagicMock()
    mock_account.id = uuid.uuid4()

    mock_job_repo = AsyncMock()
    mock_job_repo.create_job = AsyncMock(return_value=mock_job)
    mock_job_repo.emit_event = AsyncMock()
    mock_job_repo.update_job = AsyncMock()

    mock_account_repo = AsyncMock()
    mock_account_repo.upsert = AsyncMock(return_value=mock_account)

    mock_rel_repo = AsyncMock()
    mock_rel_repo.upsert = AsyncMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session_cm)

    return mock_factory, mock_job, mock_job_repo, mock_account_repo, mock_rel_repo


def _make_mock_pool(page: AsyncMock | None = None):
    """Return (mock_pool_class, mock_pool_instance, mock_page)."""
    mock_page = page or AsyncMock()
    page_cm = AsyncMock()
    page_cm.__aenter__ = AsyncMock(return_value=mock_page)
    page_cm.__aexit__ = AsyncMock(return_value=False)

    mock_pool = AsyncMock()
    mock_pool.page_context = MagicMock(return_value=page_cm)

    pool_cm = AsyncMock()
    pool_cm.__aenter__ = AsyncMock(return_value=mock_pool)
    pool_cm.__aexit__ = AsyncMock(return_value=False)

    return pool_cm, mock_pool, mock_page


def _success_result(username: str, mentions: list[str] | None = None) -> ScrapeResult:
    return ScrapeResult(
        username=username,
        profile=_make_profile(username),
        tweets=[
            TweetData(
                tweet_id="1",
                text=" ".join(f"@{m}" for m in (mentions or [])),
                timestamp=None,
                mentions=mentions or [],
            )
        ]
        if mentions
        else [],
        cross_platform={},
        success=True,
    )


def _failed_result(username: str) -> ScrapeResult:
    return ScrapeResult(
        username=username,
        profile=_empty_profile(),
        success=False,
        error="navigation failed",
    )


# ---------------------------------------------------------------------------
# AccountCrawler
# ---------------------------------------------------------------------------


class TestAccountCrawler:
    async def test_run_returns_job_id(self):
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_success_result("alice")),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            job_id = await crawler.run()

        assert isinstance(job_id, uuid.UUID)
        assert job_id == mock_job.id

    async def test_run_creates_and_finalizes_job(self):
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_success_result("alice")),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        mock_job_repo.create_job.assert_called_once()
        # update_job is called per-account (live counter) AND at finalize; the
        # finalize call (last) sets status=COMPLETED.
        assert mock_job_repo.update_job.called
        _, kwargs = mock_job_repo.update_job.call_args
        from storage.models.job import JobStatus
        assert kwargs["status"] == JobStatus.COMPLETED

    async def test_run_scrapes_seed_account(self):
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        mock_scrape = AsyncMock(return_value=_success_result("alice"))
        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        # scrape_account called for the seed
        mock_scrape.assert_called_once()
        call_args = mock_scrape.call_args
        assert call_args[0][1] == "alice"  # positional arg: username

    async def test_run_bfs_enqueues_mentions(self):
        """Seed mentions 'bob' → bob should also be scraped at depth=1."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=1, max_accounts=10)

        scraped_usernames: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped_usernames.append(username)
            if username == "alice":
                return _success_result("alice", mentions=["bob"])
            return _success_result(username)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        assert "alice" in scraped_usernames
        assert "bob" in scraped_usernames

    async def test_run_expands_via_following(self):
        """Seed follows 'bob' → bob enqueued/scraped and a FOLLOWS edge stored."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=1, max_accounts=10)

        scraped: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped.append(username)
            if username == "alice":
                result = _success_result("alice")
                result.following = ["bob"]
                return result
            return _success_result(username)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        assert "alice" in scraped
        assert "bob" in scraped
        from storage.models.relationship import RelType

        rel_types = [c.args[2] for c in mock_rr.upsert.call_args_list]
        assert RelType.FOLLOWS in rel_types

    async def test_run_expands_via_followers(self):
        """A follower 'zoe' → zoe enqueued/scraped via an inbound FOLLOWS edge."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=1, max_accounts=10)

        scraped: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped.append(username)
            if username == "alice":
                result = _success_result("alice")
                result.followers = ["zoe"]
                return result
            return _success_result(username)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        assert "alice" in scraped
        assert "zoe" in scraped
        # an inbound FOLLOWS edge to the seed was recorded on the graph
        edge_calls = [c.args for c in mock_graph.upsert_edge.call_args_list]
        assert any(args[2] == "FOLLOWS" for args in edge_calls)

    async def test_run_respects_max_depth(self):
        """max_depth=0 → only seed scraped; mentions not enqueued."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=10)

        scraped_usernames: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped_usernames.append(username)
            return _success_result(username, mentions=["bob", "carol"])

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        # With max_depth=0, alice scraped but bob/carol not enqueued
        assert scraped_usernames == ["alice"]

    async def test_run_respects_max_accounts(self):
        """max_accounts=1 → stops after seed even if mentions discovered."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=2, max_accounts=1)

        scraped_usernames: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped_usernames.append(username)
            return _success_result(username, mentions=["bob"])

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        assert len(scraped_usernames) == 1
        assert scraped_usernames[0] == "alice"

    async def test_run_skips_duplicate_handles(self):
        """Same handle mentioned twice → scraped only once."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=1, max_accounts=10)

        scraped_usernames: list[str] = []

        async def mock_scrape(page, username, *, bucket, rate_profile, **kwargs):
            scraped_usernames.append(username)
            if username == "alice":
                # mentions bob twice (alice and bob both mention bob at depth 1)
                result = _success_result("alice", mentions=["bob"])
                return result
            return _success_result(username)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch("scraper.jobs.crawler.scrape_account", new=mock_scrape),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        # bob should appear exactly once
        assert scraped_usernames.count("bob") == 1

    async def test_run_handles_scrape_failure(self):
        """Failed scrape → job continues (COMPLETED, not FAILED)."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_failed_result("alice")),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()  # must not raise

        _, kwargs = mock_job_repo.update_job.call_args
        from storage.models.job import JobStatus
        assert kwargs["status"] == JobStatus.COMPLETED

    async def test_graph_node_upserted(self):
        """Successful scrape → graph upsert_node called for the account."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_success_result("alice")),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        mock_graph.upsert_node.assert_called()
        first_call = mock_graph.upsert_node.call_args_list[0]
        node_id = first_call[0][0]
        assert node_id == "twitter:@alice"

    async def test_run_emits_live_progress(self):
        """Live events + counter: account_started/account_scraped emitted and the
        accounts_scraped counter is bumped per-account (before finalize)."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_success_result("alice", mentions=["bob"])),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        event_types = [c.args[1] for c in mock_job_repo.emit_event.call_args_list]
        assert "job_started" in event_types
        assert "account_started" in event_types
        assert "account_scraped" in event_types
        assert "job_finished" in event_types

        # A per-account counter bump (accounts_scraped, no status) precedes finalize.
        assert any(
            c.kwargs.get("accounts_scraped") and "status" not in c.kwargs
            for c in mock_job_repo.update_job.call_args_list
        )

    async def test_run_emits_account_failed_on_soft_failure(self):
        """A failed scrape (success=False) emits an account_failed event."""
        mock_factory, mock_job, mock_job_repo, mock_ar, mock_rr = _make_mock_session_factory()
        pool_cm, mock_pool, mock_page = _make_mock_pool()
        mock_graph = AsyncMock()
        config = CrawlerConfig(seed_username="alice", max_depth=0, max_accounts=1)

        with (
            patch("scraper.jobs.crawler.BrowserPool", return_value=pool_cm),
            patch("scraper.jobs.crawler.JobRepository", return_value=mock_job_repo),
            patch("scraper.jobs.crawler.AccountRepository", return_value=mock_ar),
            patch("scraper.jobs.crawler.RelationshipRepository", return_value=mock_rr),
            patch(
                "scraper.jobs.crawler.scrape_account",
                new=AsyncMock(return_value=_failed_result("alice")),
            ),
        ):
            crawler = AccountCrawler(config, mock_factory, mock_graph)
            await crawler.run()

        event_types = [c.args[1] for c in mock_job_repo.emit_event.call_args_list]
        assert "account_failed" in event_types
