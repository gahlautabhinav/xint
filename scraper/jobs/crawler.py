from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graph.backends.base import AbstractGraphBackend
from graph.schema.nodes import make_node_id
from scraper.browser.pool import BrowserConfig, BrowserPool
from scraper.jobs.worker import ScrapeResult, scrape_account
from scraper.proxy.models import Proxy, ProxyHealth
from scraper.proxy.rotator import ProxyRotator
from scraper.ratelimit.profiles import ProfileName, get_profile
from scraper.ratelimit.token_bucket import TokenBucket
from storage.models.job import CrawlJob, JobStatus
from storage.models.relationship import RelType
from storage.repositories.account_repo import AccountRepository
from storage.repositories.job_repo import JobRepository
from storage.repositories.relationship_repo import RelationshipRepository

__all__ = ["AccountCrawler", "CrawlerConfig", "CrawlJob", "JobStatus"]

logger = logging.getLogger(__name__)


async def _trigger_bias_agent(
    username: str,
    tweets: list,
    agent_url: str,
    connections: list[dict] | None = None,
) -> None:
    """POST scraped tweets to xint-bias-agent for bias classification. Fire-and-forget.

    A down or slow agent must never block or crash a crawl — all errors are logged and swallowed.
    """
    payload = {
        "username": username,
        "tweets": [
            {
                "id": t.tweet_id,
                "text": t.text,
                "timestamp": str(t.timestamp) if t.timestamp else None,
            }
            for t in tweets
        ],
        "connections": connections or [],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{agent_url}/analyze", json=payload)
    except Exception as exc:
        logger.warning("Bias agent unreachable for @%s: %s", username, exc)


@dataclass
class CrawlerConfig:
    seed_username: str
    max_depth: int = 2
    max_accounts: int = 500
    rate_profile_name: ProfileName = "moderate"
    proxy_urls: list[str] = field(default_factory=list)
    # Scrape the following list (FOLLOWS edges) — the main network signal.
    scrape_following: bool = True
    max_following: int = 50
    # Scrape the followers list (inbound FOLLOWS edges: follower → this account).
    scrape_followers: bool = True
    max_followers: int = 50
    # Enrichment ("Discover All") mode: crawl this explicit set of handles
    # instead of BFS-expanding from the seed. When set, the queue is seeded with
    # these handles (depth 0) rather than the seed username.
    target_usernames: list[str] | None = None
    # When False, newly-discovered handles are NOT enqueued — the crawl visits
    # only the initial frontier and stops (no graph growth). Used by enrichment.
    expand: bool = True


def _proxies_from_urls(urls: list[str]) -> list[Proxy]:
    proxies: list[Proxy] = []
    for url in urls:
        try:
            parsed = urlparse(url)
            if not parsed.hostname or not parsed.port:
                continue
            proxies.append(
                Proxy(
                    host=parsed.hostname,
                    port=parsed.port,
                    scheme=parsed.scheme or "http",
                    username=parsed.username,
                    password=parsed.password,
                    health=ProxyHealth(),
                )
            )
        except Exception as exc:
            logger.debug("Skipping invalid proxy URL %r: %s", url, exc)
    return proxies


class AccountCrawler:
    """BFS OSINT crawler: scrapes Twitter profiles and writes graph + storage.

    Instantiate with a config, a SQLAlchemy async session factory, and a
    graph backend. Call ``await crawler.run()`` to start the crawl.

    Returns the UUID of the created :class:`CrawlJob` record.

    Concurrency: Phase 5 runs single-threaded (one page at a time). The
    BrowserPool is used for its proxy/UA injection and stealth features.
    Parallel scraping (one coroutine per pool slot) is deferred to Phase 6.
    """

    def __init__(
        self,
        config: CrawlerConfig,
        session_factory: async_sessionmaker[AsyncSession],
        graph: AbstractGraphBackend,
        browser_config: BrowserConfig | None = None,
    ) -> None:
        self._config = config
        self._sf = session_factory
        self._graph = graph
        self._bcfg = browser_config or BrowserConfig()

    async def run(self, job_id: uuid.UUID | None = None) -> uuid.UUID:
        """Execute BFS crawl. Returns the CrawlJob ID.

        When *job_id* is given the crawler adopts that existing job row
        (created by the API endpoint so it can return a real id immediately)
        and marks it RUNNING. When omitted it creates its own job record —
        the path used by the CLI and tests.
        """
        config = self._config
        from config.settings import get_settings
        bias_agent_url: str | None = get_settings().BIAS_AGENT_URL
        rate_profile = get_profile(config.rate_profile_name)
        bucket = TokenBucket(
            capacity=rate_profile.burst_capacity,
            rate=rate_profile.requests_per_minute / 60.0,
        )
        rotator = ProxyRotator(_proxies_from_urls(config.proxy_urls))

        # Create — or adopt — the job record
        started_at = datetime.now(timezone.utc)
        async with self._sf() as session:
            job_repo = JobRepository(session)
            if job_id is None:
                job = await job_repo.create_job(
                    seed_username=config.seed_username,
                    max_depth=config.max_depth,
                    max_accounts=config.max_accounts,
                    status=JobStatus.RUNNING,
                    started_at=started_at,
                )
                job_id = job.id
            else:
                await job_repo.update_job(
                    job_id,
                    status=JobStatus.RUNNING,
                    started_at=started_at,
                )
            await job_repo.emit_event(job_id, "job_started", {"seed": config.seed_username})
            await session.commit()

        # BFS queue: (username_lowercase, depth)
        # `visited` bounds total work: the loop runs at most max_accounts iterations
        # regardless of how many succeed, preventing an infinite loop when every
        # scrape fails.
        visited: set[str] = set()
        if config.target_usernames:
            # Enrichment mode: crawl an explicit handle set (all at depth 0).
            queue = deque((u.lower(), 0) for u in config.target_usernames)
        else:
            queue = deque([(config.seed_username.lower(), 0)])
        accounts_scraped = 0  # successful scrapes only — stored in job record

        status = JobStatus.COMPLETED
        error_msg: str | None = None
        cancelled = False

        try:
            async with BrowserPool(self._bcfg) as pool:
                while queue and len(visited) < config.max_accounts:
                    username, depth = queue.popleft()
                    if username in visited:
                        continue
                    visited.add(username)

                    # Cooperative cancellation: the API flips the job's status to
                    # CANCELLED; we notice at the next iteration boundary and stop
                    # cleanly (the in-flight account, if any, has already finished).
                    async with self._sf() as session:
                        current = await JobRepository(session).get_job(job_id)
                        cancel_now = current is None or current.status == JobStatus.CANCELLED
                    if cancel_now:
                        cancelled = True
                        break

                    await self._emit(
                        job_id, "account_started", {"username": username, "depth": depth}
                    )

                    try:
                        proxy = rotator.next()
                        async with pool.page_context(
                            proxy_url=proxy.url if proxy else None
                        ) as page:
                            result = await scrape_account(
                                page,
                                username,
                                bucket=bucket,
                                rate_profile=rate_profile,
                                scrape_following=config.scrape_following,
                                max_following=config.max_following,
                                scrape_followers=config.scrape_followers,
                                max_followers=config.max_followers,
                            )

                        if proxy is not None:
                            if result.success:
                                rotator.mark_success(proxy)
                            else:
                                rotator.mark_failed(proxy)

                        new_handles = await self._store(result, depth, job_id)
                        if result.success:
                            accounts_scraped += 1
                            await self._record_progress(
                                job_id,
                                accounts_scraped,
                                {
                                    "username": username,
                                    "depth": depth,
                                    "followers": result.profile.follower_count or 0,
                                    "following": len(result.following),
                                    "followers_n": len(result.followers),
                                    "mentions": sum(len(t.mentions) for t in result.tweets),
                                    "new_edges": len(new_handles),
                                },
                            )
                            if bias_agent_url and result.tweets:
                                connections = []
                                for handle in result.following:
                                    connections.append({"target": handle.lower().lstrip("@"), "type": "follows"})
                                for handle in result.followers:
                                    connections.append({"target": handle.lower().lstrip("@"), "type": "follower"})
                                asyncio.create_task(
                                    _trigger_bias_agent(username, result.tweets, bias_agent_url, connections)
                                )
                        else:
                            await self._emit(
                                job_id,
                                "account_failed",
                                {"username": username, "depth": depth, "error": result.error},
                            )

                        if config.expand and depth < config.max_depth:
                            for handle in new_handles:
                                h = handle.lower()
                                if h not in visited:
                                    queue.append((h, depth + 1))

                    except Exception as exc:
                        # Per-account errors are isolated: log and move on.
                        # Only BrowserPool startup failure (outer try) aborts the job.
                        logger.warning(
                            "Skipping %r (depth=%d) after error: %s", username, depth, exc
                        )
                        try:
                            await self._emit(
                                job_id,
                                "account_failed",
                                {"username": username, "depth": depth, "error": str(exc)},
                            )
                        except Exception:
                            logger.debug("Could not emit account_failed for %r", username)

        except Exception as exc:
            logger.error("Crawler run failed: %s", exc)
            status = JobStatus.FAILED
            error_msg = str(exc)

        # A cooperative cancel wins over a clean completion, but never masks a
        # hard failure (FAILED stays FAILED).
        if cancelled and status != JobStatus.FAILED:
            status = JobStatus.CANCELLED

        # Finalize job
        async with self._sf() as session:
            job_repo = JobRepository(session)
            await job_repo.update_job(
                job_id,
                status=status,
                accounts_scraped=accounts_scraped,
                completed_at=datetime.now(timezone.utc),
                error_message=error_msg,
            )
            await job_repo.emit_event(
                job_id,
                "job_finished",
                {"status": status.value, "accounts_scraped": accounts_scraped},
            )
            await session.commit()

        logger.info(
            "Crawl %s: %s, scraped %d accounts", job_id, status.value, accounts_scraped
        )
        return job_id

    async def _emit(
        self,
        job_id: uuid.UUID,
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Emit a single job event in its own committed session.

        Cross-engine visibility (the API reads via a separate engine on the same
        SQLite WAL file) requires a COMMIT, not just a flush — so each live event
        opens, emits, and commits.
        """
        async with self._sf() as session:
            await JobRepository(session).emit_event(job_id, event_type, payload)
            await session.commit()

    async def _record_progress(
        self,
        job_id: uuid.UUID,
        accounts_scraped: int,
        payload: dict[str, object],
    ) -> None:
        """Bump the live ``accounts_scraped`` counter and emit ``account_scraped``.

        Both writes share one session/commit so the progress bar and event log
        advance together (and we pay one commit per account, not two).
        """
        async with self._sf() as session:
            repo = JobRepository(session)
            await repo.update_job(job_id, accounts_scraped=accounts_scraped)
            await repo.emit_event(job_id, "account_scraped", payload)
            await session.commit()

    async def _store(
        self,
        result: ScrapeResult,
        depth: int,
        job_id: uuid.UUID,
    ) -> list[str]:
        """Persist a ScrapeResult to storage + graph. Returns Twitter handles to enqueue.

        Cross-platform handles (GitHub, Instagram, etc.) are stored as
        CROSS_PLATFORM_LINK edges but NOT returned for BFS — they belong to
        different platforms and are not Twitter usernames.

        Stub Account rows are created for mentioned/replied-to accounts at
        max_depth so edges are recorded even if those accounts won't be scraped.
        ``AccountRepository.upsert`` merges cleanly when they are later crawled.

        ``upsert_node`` on the graph backend merges props — calling it with an
        empty dict for stub nodes is safe because the networkx backend unions props.
        """
        new_handles: list[str] = []
        profile = result.profile
        now = datetime.now(timezone.utc)

        self_handle = result.username.lower()

        # Collect edges: (handle, RelType). FOLLOWS comes from the following
        # list; MENTIONS/REPLIES_TO/QUOTE_TWEETS/RETWEETS from tweets. All become
        # BFS frontier handles.
        # edge_evidence: (handle, rel_type) -> up-to-10 tweet IDs as proof.
        mention_edges: list[tuple[str, RelType]] = []
        edge_evidence: dict[tuple[str, RelType], list[str]] = {}
        for handle in result.following:
            mention_edges.append((handle.lower(), RelType.FOLLOWS))
        for tweet in result.tweets:
            tid = tweet.tweet_id
            for handle in tweet.mentions:
                key = (handle.lower(), RelType.MENTIONS)
                mention_edges.append(key)
                if tid:
                    lst = edge_evidence.setdefault(key, [])
                    if len(lst) < 10:
                        lst.append(tid)
            if tweet.reply_to:
                key = (tweet.reply_to.lower(), RelType.REPLIES_TO)
                mention_edges.append(key)
                if tid:
                    lst = edge_evidence.setdefault(key, [])
                    if len(lst) < 10:
                        lst.append(tid)
            if tweet.quote_url:
                # quote_url is /username/status/12345 — extract username
                parts = tweet.quote_url.strip("/").split("/")
                if parts and parts[0]:
                    key = (parts[0].lower(), RelType.QUOTE_TWEETS)
                    mention_edges.append(key)
                    if tid:
                        lst = edge_evidence.setdefault(key, [])
                        if len(lst) < 10:
                            lst.append(tid)
            if tweet.retweeted_from:
                rt = tweet.retweeted_from.lower()
                if rt != self_handle:
                    key = (rt, RelType.RETWEETS)
                    mention_edges.append(key)
                    if tid:
                        lst = edge_evidence.setdefault(key, [])
                        if len(lst) < 10:
                            lst.append(tid)
        # Deduplicate (handle, rel_type) pairs preserving insertion order
        seen_edges: set[tuple[str, RelType]] = set()
        deduped_edges: list[tuple[str, RelType]] = []
        for pair in mention_edges:
            if pair not in seen_edges:
                seen_edges.add(pair)
                deduped_edges.append(pair)

        # Inbound followers: each follower --FOLLOWS--> this account (reversed).
        follower_handles: list[str] = []
        seen_followers: set[str] = set()
        for handle in result.followers:
            h = handle.lower()
            if h == self_handle or h in seen_followers:
                continue
            seen_followers.add(h)
            follower_handles.append(h)

        async with self._sf() as session:
            account_repo = AccountRepository(session)
            rel_repo = RelationshipRepository(session)

            # Collect tweet geo locations (deduplicated, non-null only)
            geo_locations = list(dict.fromkeys(
                tw.geo_location for tw in result.tweets if tw.geo_location
            ))

            # Aggregate hashtags across this account's tweets → top-20 {tag, count}.
            # Feeds the cross-account hashtag co-occurrence overlay.
            hashtag_counts: Counter[str] = Counter()
            for tw in result.tweets:
                for tag in tw.hashtags:
                    hashtag_counts[tag.lower()] += 1
            hashtags = [
                {"tag": tag, "count": count}
                for tag, count in hashtag_counts.most_common(20)
            ]

            account = await account_repo.upsert(
                username=result.username,
                platform="twitter",
                display_name=profile.display_name,
                bio=profile.bio,
                website=profile.website,
                location=profile.location,
                profile_image_url=profile.profile_image_url,
                followers_count=profile.follower_count or 0,
                following_count=profile.following_count or 0,
                tweet_count=profile.tweet_count or 0,
                is_verified=profile.is_verified,
                scraped_at=now,
                scrape_depth=depth,
                raw_data={
                    "success": result.success,
                    "error": result.error,
                    "join_date": profile.join_date,
                    "emails": result.contacts.get("emails", []),
                    "phones": result.contacts.get("phones", []),
                    "geo_locations": geo_locations,
                    "hashtags": hashtags,
                    # {} (not None) on failed scrapes — matches the empty-container
                    # convention used for emails/phones above, so consumers can
                    # safely do raw_data["timezone"].get(...).
                    "timezone": result.activity or {},
                },
            )

            for handle, rel_type in deduped_edges:
                tweet_ids = edge_evidence.get((handle, rel_type), [])
                meta = (
                    {"tweet_ids": tweet_ids, "source_handle": self_handle}
                    if tweet_ids else None
                )
                target = await account_repo.upsert(username=handle, platform="twitter")
                await rel_repo.upsert(account.id, target.id, rel_type, metadata_=meta)
                new_handles.append(handle)

            for handle in follower_handles:
                follower = await account_repo.upsert(username=handle, platform="twitter")
                await rel_repo.upsert(follower.id, account.id, RelType.FOLLOWS)
                new_handles.append(handle)

            for platform, handle in result.cross_platform.items():
                target = await account_repo.upsert(username=handle, platform=platform)
                await rel_repo.upsert(
                    account.id,
                    target.id,
                    RelType.CROSS_PLATFORM_LINK,
                    metadata_={"platform": platform},
                )

            await session.commit()

        # Graph upserts (no transaction — networkx is in-memory)
        src_id = make_node_id("twitter", result.username)
        await self._graph.upsert_node(
            src_id,
            ["Account"],
            {
                "display_name": profile.display_name or "",
                "bio": profile.bio or "",
                "followers_count": profile.follower_count or 0,
                "is_verified": profile.is_verified,
                "scrape_depth": depth,
            },
        )
        for handle, rel_type in deduped_edges:
            dst_id = make_node_id("twitter", handle)
            await self._graph.upsert_node(dst_id, ["Account"], {})
            edge_props: dict[str, object] = {"weight": 1.0}
            tweet_ids = edge_evidence.get((handle, rel_type), [])
            if tweet_ids:
                edge_props["tweet_ids"] = tweet_ids
                edge_props["source_handle"] = self_handle
            await self._graph.upsert_edge(src_id, dst_id, rel_type.value, edge_props)

        for handle in follower_handles:
            f_id = make_node_id("twitter", handle)
            await self._graph.upsert_node(f_id, ["Account"], {})
            await self._graph.upsert_edge(f_id, src_id, "FOLLOWS", {"weight": 1.0})

        for platform, handle in result.cross_platform.items():
            dst_id = make_node_id(platform, handle)
            await self._graph.upsert_node(dst_id, ["Account"], {"platform": platform})
            await self._graph.upsert_edge(
                src_id, dst_id, "CROSS_PLATFORM_LINK", {"weight": 1.0, "platform": platform}
            )

        return new_handles
