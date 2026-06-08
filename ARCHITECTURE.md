# TwitterOSINT — Production-Grade System Architecture

**Version:** 2.0
**Date:** 2026-06-08
**Status:** Implemented — all phases complete
**License:** MIT

---

## 1. Executive Technical Summary

### Architecture Overview and Philosophy

TwitterOSINT is a **local-first, modular monolith** OSINT tool. The single-repo structure prioritizes contributor onboarding velocity and operational simplicity — a contributor can clone one repo, run one `docker-compose up`, and have a working system. The architecture enforces hard module boundaries so that each directory can be extracted into a standalone service later without rewrites.

The system is designed around three core realities:

1. **The scraping surface is fragile.** Twitter/X changes its DOM, JavaScript bundles, and anti-bot mechanisms frequently. The scraper module must be maximally isolatable so changes there do not cascade into graph, storage, or API layers.

2. **The tool operates locally, not as a hosted SaaS.** There is no multi-tenancy, no remote database, no cloud dependency. All data stays on the operator's machine. Infrastructure complexity must be proportional to this reality.

3. **Graph traversal is the core product.** Every other component exists to feed the graph or query it. Graph quality, traversal depth control, and relationship accuracy are the primary success criteria.

### Scalability Profile

Target: Single-operator local use. 1-50 concurrent scrape jobs. Graphs of 10,000-500,000 nodes are realistic for deep crawls. The architecture handles this without distributed systems. At 1M+ nodes, Neo4j sharding or migration to a hosted graph DB becomes relevant — that is a future concern.

### Key Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| X DOM changes break scraper | High | Strict selector abstraction, selector version registry |
| Proxy pool exhaustion or failure | High | Graceful degradation to direct (with warning), proxy health scoring |
| SQLite write contention under parallel jobs | Medium | WAL mode + per-job transaction isolation |
| Neo4j memory pressure on large graphs | Medium | Configurable memory limits, networkx fallback |
| Rate limiting / account bans | High | Human-like delay profiles, session rotation strategy |

---

## 2. High-Level Architecture

### Component Map

```
osint-twitter/
├── scraper/            # Data acquisition layer
│   ├── browser/        # Playwright pool, session management
│   ├── extractors/     # Per-platform data extractors (twitter, instagram, github...)
│   ├── proxy/          # Proxy loader, health checker, rotation strategy
│   ├── ratelimit/      # Token bucket, delay profiles
│   └── jobs/           # Job queue, retry logic, job state machine
│
├── graph/              # Graph intelligence layer
│   ├── backends/       # Neo4j adapter, networkx adapter (common interface)
│   ├── schema/         # Node/edge type definitions
│   ├── algorithms/     # BFS/DFS traversal, community detection, similarity scoring
│   └── builder/        # Translates raw scraped data into graph mutations
│
├── storage/            # Relational persistence layer
│   ├── models/         # SQLAlchemy ORM models
│   ├── migrations/     # Alembic migration scripts
│   ├── repositories/   # Repository pattern per entity type
│   └── engine.py       # DB engine factory (SQLite vs Postgres)
│
├── api/                # HTTP interface layer
│   ├── routers/        # FastAPI route modules
│   ├── schemas/        # Pydantic request/response models
│   ├── dependencies/   # FastAPI dependency injection (DB session, graph conn)
│   └── main.py         # App factory
│
├── cli/                # CLI interface layer
│   ├── commands/       # Click command groups
│   └── formatters/     # Output formatters (JSON, CSV, table)
│
├── frontend/           # Graph visualization UI
│   ├── src/
│   │   ├── components/ # React components
│   │   ├── hooks/      # Custom hooks (graph state, SSE)
│   │   ├── stores/     # Zustand stores
│   │   └── lib/        # Cytoscape.js config, API client
│   └── public/
│
├── config/             # Configuration system
│   ├── settings.py     # Pydantic Settings model
│   ├── proxies.txt     # User-supplied proxy list (gitignored)
│   ├── cookies.json    # Persisted browser sessions (gitignored)
│   └── ua_pool.txt     # User-agent strings pool
│
├── tests/              # Test suite (mirrors module structure)
├── docker/             # Dockerfiles per component
├── docker-compose.yml  # Full local dev stack
├── docker-compose.neo4j.yml  # Neo4j addon
└── pyproject.toml      # Python project config
```

### Data Flow Overview

```
User Input (seed username)
        |
        v
   CLI / Frontend
        |
        v
    API Layer (FastAPI)
        |
        v
   Job Queue (SQLite-backed)
        |
        v
   Scraper Engine
   (Playwright browser pool)
        |
        v
   Raw Data (JSON blobs)
        |
     /     \
    v       v
Storage   Graph Builder
(SQLAlchemy) (Neo4j / networkx)
    |           |
    v           v
    API reads both layers
        |
        v
   CLI / Frontend renders
```

### Architecture Diagram (Mermaid)

```mermaid
graph TD
    USER[User: CLI or Browser]
    API[FastAPI API Layer]
    JOBS[Job Queue<br/>SQLite-backed]
    SCRAPER[Scraper Engine<br/>Playwright Pool]
    PROXY[Proxy Manager]
    SESSION[Session Store<br/>cookies.json]
    EXTRACTOR[Extractors<br/>Twitter / Instagram / GitHub]
    STORAGE[Storage Layer<br/>SQLAlchemy ORM]
    SQLITE[(SQLite / Postgres)]
    GRAPHBUILDER[Graph Builder]
    GRAPHDB[(Neo4j / networkx)]
    FRONTEND[React Frontend<br/>Cytoscape.js]

    USER -->|HTTP| API
    API --> JOBS
    JOBS --> SCRAPER
    SCRAPER --> PROXY
    SCRAPER --> SESSION
    SCRAPER --> EXTRACTOR
    EXTRACTOR -->|raw JSON| STORAGE
    EXTRACTOR -->|raw JSON| GRAPHBUILDER
    STORAGE --> SQLITE
    GRAPHBUILDER --> GRAPHDB
    API -->|query| STORAGE
    API -->|query| GRAPHDB
    API -->|SSE job events| FRONTEND
    FRONTEND -->|HTTP + SSE| API
```

---

## 3. Module Breakdown — Full Detail

---

### 3.1 `scraper/` — Data Acquisition Layer

**Responsibility:** Everything between "we want data about account X" and "raw JSON payload is available for processing." This module knows nothing about graph schemas or SQL models.

**Public Interface (Python API, called by `api/` and job workers):**

```python
# scraper/__init__.py
from scraper.jobs import JobQueue, Job
from scraper.browser import BrowserPool
from scraper.extractors import TwitterExtractor, InstagramExtractor, GitHubExtractor
```

#### 3.1.1 `scraper/browser/`

**Files:**

```
scraper/browser/
├── pool.py          # BrowserPool: manages N Playwright browser instances
├── session.py       # SessionManager: loads/saves cookies.json per identity
├── fingerprint.py   # FingerprintRotator: viewport, timezone, WebGL noise
└── page_utils.py    # Human-like interaction helpers (scroll, hover, delays)
```

**`pool.py` — BrowserPool:**

```python
class BrowserPool:
    """
    Manages a pool of Playwright browser contexts.
    Each context = one "identity" (UA + proxy + cookies).
    Contexts are checked out, used, returned. Poisoned contexts are discarded.
    """
    def __init__(self, size: int, proxy_manager: ProxyManager)
    async def checkout(self) -> BrowserContext  # blocks until one is free
    async def checkin(self, ctx: BrowserContext, poisoned: bool = False)
    async def shutdown(self)
```

Key decisions:
- `playwright.async_api` throughout — all scraping is async
- Pool size default: 3 (configurable). Above 5 on a single IP risks detection.
- Each context uses a distinct proxy + UA combination
- Contexts are rotated after N pages (configurable, default: 10) to avoid fingerprint drift

**`session.py` — SessionManager:**

```python
class SessionManager:
    """
    Persists and restores browser authentication state (cookies, localStorage).
    Supports multiple named identities (e.g., "anon_1", "auth_user_A").
    """
    def load(self, identity: str) -> dict | None
    def save(self, identity: str, state: dict)
    def invalidate(self, identity: str)
    def list_valid(self) -> list[str]
```

Storage: `config/sessions/{identity}.json`. gitignored. Never committed.

**`fingerprint.py` — FingerprintRotator:**

Generates browser launch arguments that vary:
- `window.navigator.userAgent` via `extra_http_headers`
- Viewport dimensions (from a pool of real screen resolutions)
- Timezone (random from common pool: US/EST, US/PST, Europe/London, etc.)
- `accept-language` header variation

Libraries: `playwright`, `fake-useragent` (fallback: static `ua_pool.txt`)

**`page_utils.py` — Human interaction simulation:**

```python
async def human_scroll(page, distance: int, variance: float = 0.3)
async def human_delay(min_ms: int = 2000, max_ms: int = 8000)
async def human_click(page, selector: str)
async def wait_for_network_idle(page, timeout: int = 10000)
```

Uses `random.gauss()` for delay variance, not `random.uniform()` — Gaussian distribution matches human behavior more accurately.

---

#### 3.1.2 `scraper/proxy/`

```
scraper/proxy/
├── loader.py        # Reads proxies.txt, dev scraper (proxyscrape.com)
├── health.py        # Async health checker (test URLs, latency scoring)
├── rotator.py       # Rotation strategy (round-robin, weighted by health score)
└── models.py        # Proxy dataclass with health fields
```

**`loader.py`:**

```python
class ProxyLoader:
    def load_from_file(self, path: str) -> list[Proxy]
    async def fetch_free_proxies(self) -> list[Proxy]  # proxyscrape.com API
    def get_all(self) -> list[Proxy]
```

`proxyscrape.com` endpoint: `https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&anonymity=elite`

**`health.py`:**

```python
class ProxyHealthChecker:
    TEST_URLS = ["https://httpbin.org/ip", "https://api.ipify.org"]

    async def check(self, proxy: Proxy) -> ProxyHealth
    async def check_all(self, proxies: list[Proxy]) -> list[Proxy]  # filters dead ones
```

Health scoring fields: `latency_ms`, `success_rate` (rolling 10-request window), `last_checked_at`, `is_alive`.

**`rotator.py`:**

```python
class ProxyRotator:
    """
    Strategy: weighted random selection by health score.
    Dead proxies are excluded. Proxies scoring < 30% success rate are demoted.
    On total pool exhaustion: falls back to direct connection with a warning log.
    """
    def next(self) -> Proxy | None
    def mark_failed(self, proxy: Proxy)
    def mark_success(self, proxy: Proxy)
```

---

#### 3.1.3 `scraper/ratelimit/`

```
scraper/ratelimit/
├── token_bucket.py  # Per-domain token bucket rate limiter
├── profiles.py      # Named delay profiles (conservative, moderate, aggressive)
└── backoff.py       # Exponential backoff with jitter for retries
```

**`token_bucket.py`:**

```python
class TokenBucket:
    """
    Async-safe token bucket. One bucket per domain.
    Default: 1 request per 4 seconds for twitter.com
    """
    def __init__(self, rate: float, capacity: int)
    async def consume(self, tokens: int = 1)  # blocks until tokens available
```

**`profiles.py`:** Named configurations the user selects via config:

| Profile | Requests/min | Base delay | Use case |
|---------|-------------|------------|----------|
| `conservative` | 5 | 8-15s | Stealth, no proxy |
| `moderate` | 12 | 3-8s | Default with proxies |
| `aggressive` | 25 | 1-3s | Fast, high proxy quality required |

**`backoff.py`:**

```python
def exponential_backoff(attempt: int, base: float = 2.0, max_wait: float = 120.0) -> float:
    """Full jitter: random.uniform(0, min(max_wait, base ** attempt))"""
```

Full jitter (not additive jitter) — prevents thundering herd across parallel jobs.

---

#### 3.1.4 `scraper/extractors/`

```
scraper/extractors/
├── base.py          # AbstractExtractor interface
├── twitter.py       # TwitterExtractor — profile, tweets, following, mentions
├── instagram.py     # InstagramExtractor — public profile only
├── github.py        # GitHubExtractor — public profile, repos
├── linkedin.py      # LinkedInExtractor — stub (highly anti-bot, limited)
├── tiktok.py        # TikTokExtractor — public profile
└── cross_platform.py  # CrossPlatformDetector — bio/link parsing
```

**`base.py`:**

```python
class AbstractExtractor(ABC):
    @abstractmethod
    async def extract_profile(self, identifier: str) -> RawProfile

    @abstractmethod
    async def extract_connections(self, identifier: str) -> RawConnections

    @abstractmethod
    async def supports(self, platform: str) -> bool
```

`RawProfile` and `RawConnections` are plain `TypedDict` structures — no ORM models, no graph nodes. The extractor layer is intentionally dumb about what downstream does with data.

**`twitter.py` — TwitterExtractor:**

Key extraction targets and selectors (as of design date — must be versioned):

```python
SELECTOR_REGISTRY = {
    "v1": {
        # Profile page selectors
        "display_name": '[data-testid="UserName"] span',
        "bio": '[data-testid="UserDescription"]',
        "following_count": 'a[href$="/following"] span',
        "followers_count": 'a[href$="/followers"] span',
        "location": '[data-testid="UserLocation"]',
        "website": '[data-testid="UserUrl"] a',
        # Tweet selectors
        "tweet_text": '[data-testid="tweetText"]',
        "tweet_author": '[data-testid="User-Name"]',
        "mention_in_tweet": 'a[href^="/"]',  # filtered for @handle pattern
    }
}
```

The `SELECTOR_REGISTRY` is the critical abstraction. When X changes its DOM, contributors update one versioned dict rather than hunting through scattered code.

Extraction methods:

```python
class TwitterExtractor(AbstractExtractor):
    async def extract_profile(self, username: str) -> RawProfile
    async def extract_following(self, username: str, limit: int = 200) -> list[str]
    async def extract_followers(self, username: str, limit: int = 200) -> list[str]
    async def extract_tweets(self, username: str, limit: int = 100) -> list[RawTweet]
    async def extract_mentions(self, tweet: RawTweet) -> list[str]
    async def extract_interactions(self, username: str) -> list[RawInteraction]

    async def _infinite_scroll_collect(self, page, item_selector: str, limit: int) -> list
    async def _handle_age_gate(self, page) -> bool
    async def _detect_rate_limit_page(self, page) -> bool  # returns True if blocked
```

**`cross_platform.py` — CrossPlatformDetector:**

Parses bio text, website fields, and pinned tweet links for handles/URLs on other platforms.

```python
PLATFORM_PATTERNS = {
    "instagram": [
        r"(?:instagram\.com/|ig:|insta:)\s*@?([\w.]+)",
        r"@([\w.]+)\s+on\s+instagram",
    ],
    "github": [
        r"github\.com/([\w-]+)",
        r"gh:\s*([\w-]+)",
    ],
    "linkedin": [
        r"linkedin\.com/in/([\w-]+)",
        r"linkedin\.com/pub/([\w-]+)",
    ],
    "tiktok": [
        r"tiktok\.com/@([\w.]+)",
        r"@([\w.]+)\s+on\s+tiktok",
    ],
    "youtube": [
        r"youtube\.com/(?:@|c/|user/)([\w-]+)",
        r"youtu\.be/([\w-]+)",
    ],
}

class CrossPlatformDetector:
    def detect(self, text: str) -> list[PlatformHandle]
    def detect_from_url(self, url: str) -> PlatformHandle | None
    def normalize_handle(self, platform: str, raw: str) -> str
```

`PlatformHandle` = `{"platform": str, "handle": str, "confidence": float, "source": str}`. Confidence is 1.0 for URL matches, 0.7 for regex-in-bio matches.

---

#### 3.1.5 `scraper/jobs/`

See section 10 (Job/Task System) for full detail.

---

### 3.2 `graph/` — Graph Intelligence Layer

**Responsibility:** Maintain the relationship graph, execute graph queries, run algorithms. Knows nothing about HTTP, scraping, or SQL schemas — it speaks in nodes and edges.

```
graph/
├── backends/
│   ├── base.py       # AbstractGraphBackend interface
│   ├── neo4j_backend.py
│   └── networkx_backend.py
├── schema/
│   ├── nodes.py      # Node type definitions (Account, Platform, etc.)
│   └── edges.py      # Edge type definitions (FOLLOWS, MENTIONS, etc.)
├── algorithms/
│   ├── traversal.py  # BFS/DFS with depth and visit limits
│   ├── centrality.py # Degree, betweenness, PageRank
│   ├── community.py  # Louvain community detection
│   └── similarity.py # Jaccard similarity for account clustering
├── builder/
│   └── ingestor.py   # RawProfile/RawConnections → graph mutations
└── __init__.py
```

**`backends/base.py` — AbstractGraphBackend:**

```python
class AbstractGraphBackend(ABC):
    @abstractmethod
    async def upsert_node(self, node_id: str, labels: list[str], props: dict) -> None

    @abstractmethod
    async def upsert_edge(self, src: str, dst: str, rel_type: str, props: dict) -> None

    @abstractmethod
    async def get_neighbors(self, node_id: str, rel_types: list[str] = None, depth: int = 1) -> list[dict]

    @abstractmethod
    async def get_subgraph(self, node_id: str, depth: int, limit: int) -> GraphData

    @abstractmethod
    async def run_cypher(self, query: str, params: dict) -> list[dict]  # Neo4j only

    @abstractmethod
    async def run_nx_query(self, fn: Callable) -> Any  # networkx only

    @abstractmethod
    async def node_count(self) -> int

    @abstractmethod
    async def edge_count(self) -> int
```

`GraphData` = `{"nodes": list[NodeData], "edges": list[EdgeData]}` — the wire format for both backends and the API.

**Backend selection** is controlled by `config/settings.py`:

```python
GRAPH_BACKEND: Literal["neo4j", "networkx"] = "networkx"  # default: no external deps
```

---

### 3.3 `storage/` — Relational Persistence Layer

**Responsibility:** All relational persistence — accounts, jobs, raw scraped data, configuration state. The graph DB holds the relationship topology; the relational DB holds the detailed record-level data.

```
storage/
├── models/
│   ├── account.py    # Account ORM model
│   ├── relationship.py
│   ├── job.py        # CrawlJob ORM model
│   ├── raw_data.py   # RawScrapeResult storage
│   └── platform.py   # CrossPlatformLink model
├── repositories/
│   ├── account_repo.py
│   ├── job_repo.py
│   └── relationship_repo.py
├── migrations/
│   └── versions/     # Alembic migration scripts
├── engine.py         # DB engine factory
├── base.py           # SQLAlchemy declarative base
└── session.py        # Async session factory
```

**`engine.py` — DB Engine Factory:**

```python
def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    if settings.DATABASE_URL.startswith("sqlite"):
        return create_async_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},
            # WAL mode set via event listener for SQLite
        )
    else:
        return create_async_engine(
            settings.DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
```

SQLite WAL mode is enabled via a `@event.listens_for(engine.sync_engine, "connect")` hook that executes `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`. This is essential for concurrent readers + one writer without contention.

**ORM:** `sqlalchemy[asyncio]` with `aiosqlite` for SQLite, `asyncpg` for Postgres. Using `AsyncSession` throughout. No sync sessions anywhere in the codebase — prevents accidental blocking in async contexts.

**Migrations:** Alembic with autogenerate from models. Two migration contexts: SQLite (dev, `sqlite+aiosqlite`) and Postgres (prod, `postgresql+asyncpg`). One `env.py` handles both.

---

### 3.4 `api/` — HTTP Interface Layer

See section 5 for full endpoint design.

---

### 3.5 `cli/` — CLI Interface Layer

See section 8 for full CLI design.

---

### 3.6 `config/` — Configuration System

See section 9 for full configuration design.

---

## 4. Data Models

### 4.1 Relational Models (SQLAlchemy)

**Entity Relationship Diagram:**

```
Account
  id: UUID PK
  username: str UNIQUE NOT NULL
  platform: str NOT NULL  -- "twitter", "instagram", "github", etc.
  display_name: str
  bio: str
  location: str
  website: str
  followers_count: int
  following_count: int
  tweet_count: int
  created_at: datetime  -- account creation on platform
  profile_image_url: str
  is_verified: bool
  is_protected: bool
  scraped_at: datetime  -- when WE last scraped this
  scrape_depth: int     -- how many hops from seed
  raw_data: JSON        -- full raw scraped blob, schema-free storage

Relationship
  id: UUID PK
  source_account_id: FK -> Account.id
  target_account_id: FK -> Account.id
  rel_type: enum(FOLLOWS, MENTIONS, REPLIES_TO, QUOTE_TWEETS, CROSS_PLATFORM_LINK)
  weight: float         -- interaction frequency for weighted edges
  first_seen_at: datetime
  last_seen_at: datetime
  evidence_count: int   -- number of tweets/interactions supporting this edge
  metadata: JSON        -- platform-specific extras

CrossPlatformLink
  id: UUID PK
  account_id: FK -> Account.id
  target_platform: str
  target_handle: str
  target_url: str
  confidence: float
  source_field: enum(BIO, WEBSITE, PINNED_TWEET, TWEET_BODY)
  verified: bool        -- did we successfully scrape the linked platform?
  scraped_at: datetime

CrawlJob
  id: UUID PK
  seed_username: str NOT NULL
  platform: str DEFAULT "twitter"
  status: enum(PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED)
  depth: int NOT NULL   -- max hops from seed
  max_accounts: int     -- hard cap on accounts to scrape
  include_followers: bool
  include_following: bool
  include_mentions: bool
  include_interactions: bool
  follow_cross_platform: bool
  created_at: datetime
  started_at: datetime
  completed_at: datetime
  accounts_scraped: int
  accounts_queued: int
  error_message: str
  config_snapshot: JSON  -- copy of settings at job creation time

JobQueueItem
  id: UUID PK
  job_id: FK -> CrawlJob.id
  username: str NOT NULL
  platform: str NOT NULL
  priority: int DEFAULT 0
  depth_from_seed: int
  status: enum(PENDING, RUNNING, DONE, FAILED, SKIPPED)
  attempts: int DEFAULT 0
  last_error: str
  created_at: datetime
  claimed_at: datetime
  completed_at: datetime

RawScrapeResult
  id: UUID PK
  job_id: FK -> CrawlJob.id
  account_id: FK -> Account.id (nullable -- before resolution)
  username: str
  platform: str
  payload: JSON         -- full raw extraction output
  scraped_at: datetime
  extractor_version: str  -- semver of extractor used
  selector_version: str   -- version of SELECTOR_REGISTRY used

ProxyRecord
  id: UUID PK
  address: str UNIQUE   -- host:port
  protocol: str         -- http, https, socks5
  username: str
  password: str
  is_alive: bool
  latency_ms: int
  success_count: int
  failure_count: int
  last_checked_at: datetime
  source: str           -- "file", "proxyscrape", "manual"
```

**Key indexes:**

```sql
-- Account lookups
CREATE UNIQUE INDEX ix_account_platform_username ON account(platform, username);
CREATE INDEX ix_account_scraped_at ON account(scraped_at);
CREATE INDEX ix_account_scrape_depth ON account(scrape_depth);

-- Relationship queries
CREATE INDEX ix_relationship_source ON relationship(source_account_id);
CREATE INDEX ix_relationship_target ON relationship(target_account_id);
CREATE INDEX ix_relationship_type ON relationship(rel_type);
CREATE UNIQUE INDEX ix_relationship_unique ON relationship(source_account_id, target_account_id, rel_type);

-- Job queue
CREATE INDEX ix_job_queue_status_priority ON job_queue_item(status, priority DESC, created_at ASC);
CREATE INDEX ix_job_queue_job_id ON job_queue_item(job_id);
```

---

### 4.2 Graph Schema

#### Neo4j Schema

**Node Types:**

```cypher
// Account node
(:Account {
  id: UUID,
  username: String,           // unique within platform
  platform: String,           // "twitter" | "instagram" | "github" | ...
  display_name: String,
  bio: String,
  followers_count: Integer,
  following_count: Integer,
  is_verified: Boolean,
  scrape_depth: Integer,
  scraped_at: DateTime
})

// Constraints
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
  FOR (a:Account) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT account_platform_username IF NOT EXISTS
  FOR (a:Account) REQUIRE (a.platform, a.username) IS NODE KEY;

// Index for text search
CREATE TEXT INDEX account_username_text IF NOT EXISTS FOR (a:Account) ON (a.username);
CREATE TEXT INDEX account_bio_text IF NOT EXISTS FOR (a:Account) ON (a.bio);
```

**Edge Types:**

```cypher
// FOLLOWS: A follows B on Twitter
(:Account)-[:FOLLOWS {
  first_seen_at: DateTime,
  last_verified_at: DateTime,
  job_id: UUID
}]->(:Account)

// MENTIONS: A mentioned B in a tweet
(:Account)-[:MENTIONS {
  count: Integer,           // how many times
  first_seen_at: DateTime,
  last_seen_at: DateTime,
  tweet_ids: [String]       // evidence list (capped at 10)
}]->(:Account)

// REPLIES_TO: A replied to B's tweet
(:Account)-[:REPLIES_TO {
  count: Integer,
  weight: Float,
  first_seen_at: DateTime,
  last_seen_at: DateTime
}]->(:Account)

// QUOTE_TWEETS: A quote-tweeted B
(:Account)-[:QUOTE_TWEETS {
  count: Integer,
  first_seen_at: DateTime,
  last_seen_at: DateTime
}]->(:Account)

// SAME_PERSON: A on Twitter is linked to B on Instagram (cross-platform identity)
(:Account)-[:SAME_PERSON {
  confidence: Float,        // 0.0 - 1.0
  evidence: [String],       // ["bio_link", "username_match", etc.]
  verified: Boolean
}]-(:Account)               // undirected conceptually, use merge in both directions
```

**Key Cypher queries used in production:**

```cypher
// Expand subgraph N hops from seed
MATCH (seed:Account {username: $username, platform: "twitter"})
CALL apoc.path.subgraphAll(seed, {
  maxLevel: $depth,
  relationshipFilter: "FOLLOWS>|MENTIONS>|REPLIES_TO>"
}) YIELD nodes, relationships
RETURN nodes, relationships

// Find accounts connected to both A and B (co-mentions)
MATCH (a:Account {username: $user_a})<-[:MENTIONS]-(shared)-[:MENTIONS]->(b:Account {username: $user_b})
RETURN shared, count(*) as strength ORDER BY strength DESC LIMIT 20

// Community detection (requires APOC or GDS library)
CALL gds.louvain.stream({
  nodeProjection: 'Account',
  relationshipProjection: {
    FOLLOWS: { orientation: 'UNDIRECTED' }
  }
}) YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).username AS username, communityId
```

#### networkx Schema (Fallback)

When `GRAPH_BACKEND=networkx`, the graph is an in-memory `networkx.MultiDiGraph` persisted to disk via `pickle` (development) or `graphml` (export/import).

```python
import networkx as nx

# Graph initialization
G = nx.MultiDiGraph()

# Node addition
G.add_node(
    "twitter:@elonmusk",  # node_id convention: "platform:@handle"
    id="uuid...",
    username="elonmusk",
    platform="twitter",
    display_name="Elon Musk",
    followers_count=150_000_000,
    scrape_depth=0,
)

# Edge addition
G.add_edge(
    "twitter:@elonmusk",
    "twitter:@jack",
    key="FOLLOWS",        # MultiDiGraph supports multiple edges between same pair
    rel_type="FOLLOWS",
    first_seen_at="2026-06-03",
    weight=1.0,
)

# Persistence
nx.write_graphml(G, "graph_export.graphml")
G_loaded = nx.read_graphml("graph_export.graphml")

# Also pickle for full fidelity (includes all Python types)
import pickle
with open("graph.pkl", "wb") as f:
    pickle.dump(G, f)
```

networkx limitations vs Neo4j:
- Everything is in RAM — 500K nodes = ~2-4GB memory
- No Cypher — must use networkx API
- No concurrent writes — single-process only
- Community detection via `networkx-community` or `python-louvain`
- **Recommended for:** Development, small graphs (<50K nodes), no Neo4j available

---

## 5. API Design

**Framework:** FastAPI with `uvicorn` (single-worker for local, `--workers 4` for production-like).

**Base URL:** `http://localhost:8000/api/v1`

**Auth:** None for local use. Optional `X-API-Key` header check when `API_KEY` is set in config (for network-exposed deployments).

### 5.1 Router Structure

```
api/routers/
├── jobs.py          # /jobs CRUD + control + analyze-now + sync-bias-connections
├── accounts.py      # /accounts queries
├── graph.py         # /graph subgraph + traversal + hashtags + intersection
├── enrich.py        # /enrich username enumeration, identity resolution, pivots, bias flags
├── geo.py           # /geo location geocoding + map data
└── health.py        # /health liveness + readiness (via api/main.py)
```

### 5.2 Endpoint Catalogue

#### Jobs

```
POST   /api/v1/jobs
  Request:  CreateJobRequest
  Response: JobResponse (202)
  Async: creates job row, spawns background thread, returns real job id immediately

GET    /api/v1/jobs
  Query params: limit, offset
  Response: JobListResponse

GET    /api/v1/jobs/{job_id}
  Response: JobResponse

POST   /api/v1/jobs/{job_id}/cancel   (202) — cooperative cancel (sets CANCELLED; worker stops at next BFS boundary)
DELETE /api/v1/jobs/{job_id}          (204) — delete terminal job + events + queue items

GET    /api/v1/jobs/{job_id}/events
  Query: since (sequence number)
  Response: JobEventsResponse {events, last_sequence}
  Poll-based: call with ?since=<last_sequence> to get only new events

POST   /api/v1/jobs/discover          (202) — batch-scrape uncrawled stub accounts in a seed's subgraph
POST   /api/v1/jobs/analyze-now       (202) — single-account on-demand scrape + bias classification trigger
POST   /api/v1/jobs/sync-bias-connections (202) — backfill all stored relationships to bias agent
```

**`CreateJobRequest` (Pydantic):**

```python
class CreateJobRequest(BaseModel):
    seed_username: str
    platform: str = "twitter"
    depth: int = Field(default=2, ge=1, le=4)
    max_accounts: int = Field(default=500, ge=1, le=10000)
    include_followers: bool = False
    include_following: bool = True
    include_mentions: bool = True
    include_interactions: bool = True
    follow_cross_platform: bool = False
    rate_profile: Literal["conservative", "moderate", "aggressive"] = "moderate"
```

Depth is capped at 4 — beyond that, graphs become astronomically large and scraping takes days.

#### Accounts

```
GET    /api/v1/accounts
  Query: username, platform, depth, scraped_after, limit, offset
  Response: list[AccountResponse]

GET    /api/v1/accounts/{account_id}
  Response: AccountDetailResponse (includes relationship counts)

GET    /api/v1/accounts/{account_id}/relationships
  Query: rel_type, direction (in/out/both), limit
  Response: list[RelationshipResponse]

GET    /api/v1/accounts/{account_id}/cross_platform
  Response: list[CrossPlatformLinkResponse]

GET    /api/v1/accounts/search
  Query: q (username prefix/bio text search), platform, limit
```

#### Graph

```
GET    /api/v1/graph/{handle}/subgraph
  Query: platform, depth, limit
  Response: GraphData {nodes: [], edges: []}

GET    /api/v1/graph/{handle}/neighbors
  Query: platform, depth, rel_types
  Response: NeighborsResponse

GET    /api/v1/graph/hashtags
  Query: limit, min_shared
  Response: HashtagAnalysisResponse — ranked hashtags + account pairs

GET    /api/v1/graph/intersection
  Query: seeds[] (multiple), depth, limit, platform
  Response: IntersectionResponse — Jaccard scores + common nodes + subgraph
```

#### Enrichment

```
GET    /api/v1/enrich/username?username=<handle>
  Response: UsernameEnumResponse — per-platform found/not_found/unknown across ~28 sites

GET    /api/v1/enrich/identity?username=<handle>
  Response: IdentityResponse — linked accounts from GitHub, GitLab, Keybase

GET    /api/v1/enrich/pivots/{platform}/{handle}
  Response: PivotsResponse — reverse-image links, breach hints

GET    /api/v1/enrich/bias/status
  Response: BiasStatus — whether xint-bias-agent is reachable

GET    /api/v1/enrich/bias
  Response: list[BiasAccountRow] — all classified accounts

GET    /api/v1/enrich/bias/{username}
  Response: BiasAccountRow — flags, confidence, evidence for one account
```

#### Geo

```
GET    /api/v1/geo/locations
  Query: max_new, limit, seed, depth
  Response: GeoLocationsResponse — geocoded account locations for Leaflet map
```

#### Health

```
GET    /api/v1/health/live      # liveness: always 200 if process is up
GET    /api/v1/health/ready     # readiness: checks DB connection, graph backend
GET    /api/v1/health/stats     # proxy pool health, browser pool status, queue depth
```

### 5.3 Async Patterns

All route handlers are `async def`. Database operations use `AsyncSession`. Long-running operations (scrape jobs) are never executed in the request handler — they are dispatched to the job runner.

SSE for job progress:

```python
@router.get("/jobs/{job_id}/events")
async def job_events(job_id: UUID, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        last_seen = 0
        while True:
            events = await job_repo.get_events_since(db, job_id, last_seen)
            for event in events:
                yield f"data: {event.model_dump_json()}\n\n"
                last_seen = event.sequence
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 6. Storage Abstraction

### 6.1 SQLite vs Postgres Switch

The switch is entirely driven by the `DATABASE_URL` environment variable:

```bash
# SQLite (dev default)
DATABASE_URL=sqlite+aiosqlite:///./data/osint.db

# Postgres (prod)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/osint
```

SQLAlchemy + asyncio handles both identically at the ORM layer. The only differences are:

| Concern | SQLite | Postgres |
|---------|--------|---------|
| Concurrency | WAL mode, single writer | Full concurrent writes |
| JSON columns | `JSON` type (stored as text) | `JSONB` type (indexed) |
| Full-text search | `LIKE`/`GLOB` | `pg_trgm`, `tsvector` |
| Array columns | JSON-encoded list | Native `ARRAY` type |
| Max DB size | ~280TB (practical: few GB) | Unlimited |

For columns that diverge, use `sa.event.listen` + dialect detection:

```python
from sqlalchemy.dialects import sqlite, postgresql

class Account(Base):
    raw_data = Column(
        postgresql.JSONB().with_variant(sqlite.JSON(), "sqlite")
    )
```

### 6.2 Repository Pattern

```python
class AccountRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_username(self, username: str, platform: str) -> Account | None
    async def upsert(self, data: dict) -> Account
    async def bulk_upsert(self, accounts: list[dict]) -> int  # returns count
    async def get_by_depth(self, max_depth: int, limit: int) -> list[Account]
    async def search(self, query: str, platform: str = None) -> list[Account]
    async def count(self) -> int
```

Repository classes are the only thing that touches `session.execute()`. No raw SQL in route handlers or business logic.

### 6.3 Alembic Migrations

```bash
# Initialize
alembic init storage/migrations

# Generate migration
alembic revision --autogenerate -m "add cross_platform_link table"

# Upgrade
alembic upgrade head

# Downgrade
alembic downgrade -1
```

`alembic.ini` references `DATABASE_URL` from environment. `env.py` imports the SQLAlchemy `Base` from `storage/base.py` for autogenerate.

Migration naming convention: `{revision_prefix}_{description}.py`. All migrations are reversible (`downgrade()` is never left as `pass`).

---

## 7. Frontend Architecture

### 7.1 Technology Decision: Cytoscape.js over D3.js

**Decision: Use Cytoscape.js.**

Reasoning:

| Criterion | Cytoscape.js | D3.js |
|-----------|-------------|-------|
| Graph layout algorithms | Built-in (CoSE, Dagre, etc.) | Must build or import |
| Node/edge click/hover | Built-in events | Manual SVG event wiring |
| Large graph performance | Purpose-built, handles 10K+ nodes | Degrades past ~2K nodes without WebGL |
| Learning curve for contributors | Low — graph-specific API | High — general visualization primitives |
| React integration | `react-cytoscapejs` wrapper | Direct DOM manipulation conflicts with React |
| Export | Built-in PNG/SVG | Custom |

D3.js is the right choice when you need bespoke, pixel-perfect custom visualizations. Cytoscape.js is the right choice when the visualization IS the graph. This is unambiguously a graph tool.

**WebGL fallback:** For graphs >5,000 nodes, use `cytoscape-canvas` or `sigma.js` as a swap-in renderer. This is an extension point, not a day-1 requirement.

### 7.2 Component Tree

```
App
├── NavBar (bias-agent status dot, page links)
└── Routes
    ├── / → GraphExplorer
    │   ├── GraphCanvas (Cytoscape.js, cola physics, zoom-aware labels)
    │   ├── NodeInspector (bio, follower count, edges, username-enum, focus button)
    │   ├── EdgeInspector
    │   ├── RelTypeFilter
    │   └── Legend
    ├── /jobs → JobsPage
    │   ├── NewCrawlForm
    │   └── JobList (status badges, delete button per row)
    ├── /jobs/:jobId → JobDetail
    │   ├── Live terminal-style event log (per-account stream)
    │   ├── Progress bar (live accounts_scraped counter)
    │   └── Stop / Delete buttons
    ├── /accounts → AccountsPage (searchable table)
    ├── /hashtags → HashtagsPage (co-occurrence table)
    ├── /intersection → IntersectionPage (seed inputs + Jaccard graph)
    ├── /geo → GeoMapPage (Leaflet map, Nominatim geocoding)
    ├── /bias → BiasPage
    │   ├── Agent status bar (online/offline dot)
    │   ├── Analyze Now form (single-account on-demand)
    │   └── Flags table (confidence bar, evidence, flag chips)
    └── /dossier/:platform/:handle → DossierPage
        ├── Profile card (bio, counts, location, join date)
        ├── Relationships section
        ├── Cross-platform links
        └── Bias flags card
```

### 7.3 State Management

**Library:** Zustand (not Redux). Rationale: simple, no boilerplate, async-friendly, small bundle size.

```typescript
// stores/graphStore.ts
interface GraphStore {
  nodes: CyNode[];
  edges: CyEdge[];
  selectedNodeId: string | null;
  filters: GraphFilters;

  setNodes: (nodes: CyNode[]) => void;
  setEdges: (edges: CyEdge[]) => void;
  selectNode: (id: string | null) => void;
  applyFilters: (filters: GraphFilters) => void;
  addNodes: (nodes: CyNode[]) => void;  // incremental update
  addEdges: (edges: CyEdge[]) => void;
}

// stores/jobStore.ts
interface JobStore {
  jobs: Job[];
  activeJobId: string | null;
  jobProgress: Record<string, JobProgress>;

  createJob: (params: CreateJobParams) => Promise<Job>;
  pollJobProgress: (jobId: string) => void;  // starts SSE listener
  stopPolling: (jobId: string) => void;
}
```

### 7.4 Real-time Update Pattern

Job progress is consumed via SSE. The frontend opens an `EventSource` connection to `/api/v1/jobs/{job_id}/events` when a job is active.

```typescript
// hooks/useJobEvents.ts
export function useJobEvents(jobId: string) {
  const { updateJobProgress, addNodes, addEdges } = useJobStore();

  useEffect(() => {
    const es = new EventSource(`/api/v1/jobs/${jobId}/events`);

    es.onmessage = (e) => {
      const event: JobProgressEvent = JSON.parse(e.data);

      if (event.type === "account_scraped") {
        updateJobProgress(jobId, event.progress);
        // Incrementally add new nodes/edges to the graph
        if (event.new_nodes) addNodes(event.new_nodes);
        if (event.new_edges) addEdges(event.new_edges);
      }

      if (event.type === "job_completed") {
        es.close();
      }
    };

    return () => es.close();
  }, [jobId]);
}
```

Graph updates are incremental — new nodes/edges are merged into the existing Cytoscape instance using `cy.add()`, not a full re-render. This is critical for large graphs.

### 7.5 Build System

- **Vite** (not Create React App, not Webpack) — faster HMR, native ES modules, smaller output
- **TypeScript** throughout
- **TailwindCSS** for styling — fast, consistent, contributor-friendly
- Dev proxy: Vite's `server.proxy` routes `/api` to FastAPI on port 8000

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    }
  }
})
```

---

## 8. CLI Architecture

**Library:** Click with `click-repl` for optional REPL mode.

**Design principle:** The CLI can operate in two modes:
1. **API mode (default):** Talks to a running FastAPI server. Best for interactive use while the frontend is also running.
2. **Direct mode (`--direct`):** Imports storage and graph layers directly, bypasses HTTP. Best for scripting and automation without needing a server running.

### 8.1 Command Structure

```
osint [--api-url URL] [--direct] [--output json|csv|table]

osint crawl START
  osint crawl start <username> [--depth 2] [--max-accounts 500] [--platform twitter]
                               [--follow-cross-platform] [--no-following] [--mentions]
                               [--rate conservative|moderate|aggressive]
  osint crawl status <job_id>
  osint crawl list [--status pending|running|completed]
  osint crawl pause <job_id>
  osint crawl resume <job_id>
  osint crawl cancel <job_id>

osint account
  osint account get <username> [--platform twitter]
  osint account search <query> [--platform all] [--limit 20]
  osint account connections <username> [--type follows|mentions|all] [--depth 1]
  osint account cross-platform <username>

osint graph
  osint graph stats
  osint graph subgraph <username> [--depth 2] [--format json|graphml]
  osint graph path <source> <target>
  osint graph communities [--algorithm louvain]

osint export
  osint export accounts [--format csv|json] [--output FILE] [--platform twitter]
  osint export relationships [--format csv|json] [--output FILE]
  osint export graph [--format graphml|json] [--output FILE]

osint config
  osint config show
  osint config set <key> <value>
  osint config proxy test
  osint config proxy refresh  -- re-fetches free proxies from proxyscrape.com
  osint config session list
  osint config session clear
```

### 8.2 Output Formatters

```python
# cli/formatters/
class TableFormatter:     # rich.table — colored, human-readable
class JSONFormatter:      # json.dumps with indent=2
class CSVFormatter:       # csv.DictWriter to stdout or file
class GraphMLFormatter:   # networkx graphml string
```

The `--output` flag selects the formatter. Default is `table` for interactive use, `json` for piped use (detected via `sys.stdout.isatty()`).

---

## 9. Configuration System

**Library:** `pydantic-settings` — reads from environment variables and `.env` file with full type validation.

### 9.1 Settings Model

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/osint.db"

    # Graph backend
    GRAPH_BACKEND: Literal["neo4j", "networkx"] = "networkx"
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Scraper
    BROWSER_POOL_SIZE: int = Field(default=3, ge=1, le=10)
    RATE_PROFILE: Literal["conservative", "moderate", "aggressive"] = "moderate"
    DEFAULT_DEPTH: int = Field(default=2, ge=1, le=4)
    DEFAULT_MAX_ACCOUNTS: int = Field(default=500, ge=1, le=10000)
    SELECTOR_VERSION: str = "v1"  # which SELECTOR_REGISTRY version to use

    # Proxy
    PROXY_FILE: str = "config/proxies.txt"
    PROXY_REFRESH_ON_STARTUP: bool = False
    PROXY_MIN_POOL_SIZE: int = 5  # warn if below this

    # Sessions
    SESSION_DIR: str = "config/sessions"

    # Anti-detection
    UA_POOL_FILE: str = "config/ua_pool.txt"
    HUMAN_DELAY_MIN_MS: int = 2000
    HUMAN_DELAY_MAX_MS: int = 8000

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_KEY: str | None = None  # if set, required on all requests

    # Data
    DATA_DIR: str = "./data"
    MAX_RAW_DATA_AGE_DAYS: int = 30  # purge raw blobs older than this

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str | None = None  # None = stdout only
```

### 9.2 Configuration File Hierarchy

```
config/
├── proxies.txt        # One proxy per line: http://host:port or user:pass@host:port
├── ua_pool.txt        # One UA string per line (300+ included in repo)
├── sessions/          # Auto-created at runtime, gitignored
│   ├── anon_1.json
│   └── anon_2.json
.env                   # User-created, gitignored, overrides defaults
.env.example           # Committed to repo with placeholder values
```

### 9.3 `proxies.txt` Format

```
# Lines starting with # are comments
# Supported formats:
http://1.2.3.4:8080
https://1.2.3.4:8080
socks5://1.2.3.4:1080
http://user:password@1.2.3.4:8080
```

The `ProxyLoader` supports all four formats. Malformed lines are skipped with a warning log.

---

## 10. Job/Task System

**Design decision: SQLite-backed job queue, no external broker (no Celery, no Redis).**

Rationale: This is a local tool. Adding Redis as a dependency for a single-operator scraper is overengineering. SQLite WAL mode supports concurrent read + write patterns needed here. The job runner is a simple async task launched by the API server on startup.

When the system needs to scale beyond single-machine (e.g., distributed scraping fleet), this is the first component to extract — replace SQLite queue with Redis + Celery. The `JobQueue` interface is designed for that swap.

### 10.1 Job State Machine

```
PENDING -> RUNNING -> COMPLETED
    |          |
CANCELLED   PAUSED -> RUNNING
                |
             FAILED
```

State transitions are atomic via database row-level locking (`SELECT ... FOR UPDATE` on Postgres, `BEGIN IMMEDIATE` on SQLite).

### 10.2 Job Queue Implementation

```python
# scraper/jobs/queue.py

class JobQueue:
    """
    SQLite-backed FIFO queue with priority support.
    Uses polling (1s interval) rather than LISTEN/NOTIFY (Postgres-only).
    Workers claim items via optimistic locking to prevent double-processing.
    """

    async def enqueue(self, job_id: UUID, username: str, platform: str,
                      depth: int, priority: int = 0) -> JobQueueItem

    async def claim_next(self, worker_id: str) -> JobQueueItem | None
    """
    Atomically marks one PENDING item as RUNNING with this worker_id.
    Uses: UPDATE ... WHERE status='PENDING' LIMIT 1 RETURNING *
    SQLite: serialized via WAL + transaction
    """

    async def complete(self, item_id: UUID, result: dict)
    async def fail(self, item_id: UUID, error: str, retry: bool = True)
    async def requeue_stale(self, stale_after_seconds: int = 300)
    """Reclaims items that have been RUNNING too long — handles dead workers."""
```

### 10.3 Job Runner

```python
# scraper/jobs/runner.py

class JobRunner:
    """
    Single async task that drives the job queue.
    Spawns N worker coroutines (one per browser pool slot).
    Started by api/main.py on app startup via asyncio.create_task().
    """

    def __init__(self, queue: JobQueue, browser_pool: BrowserPool,
                 settings: Settings):
        self.queue = queue
        self.pool = browser_pool
        self.workers: list[asyncio.Task] = []

    async def start(self):
        for i in range(self.pool.size):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(task)

    async def stop(self):
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

    async def _worker(self, worker_id: str):
        while True:
            item = await self.queue.claim_next(worker_id)
            if item is None:
                await asyncio.sleep(1.0)
                continue

            try:
                await self._process_item(item)
            except asyncio.CancelledError:
                await self.queue.fail(item.id, "worker cancelled", retry=True)
                raise
            except Exception as e:
                retry = item.attempts < 3
                await self.queue.fail(item.id, str(e), retry=retry)
                logger.exception(f"Worker {worker_id} failed on {item.username}")

    async def _process_item(self, item: JobQueueItem):
        # 1. Check out browser context from pool
        # 2. Run appropriate extractor
        # 3. Store raw result to RawScrapeResult
        # 4. Trigger graph builder ingestor
        # 5. Detect cross-platform links, enqueue follow-up items if enabled
        # 6. Emit SSE event for job progress
        # 7. Check depth limit before enqueueing discovered accounts
```

### 10.4 Depth Control and Explosion Prevention

BFS depth control is critical. Without it, a depth-3 crawl on a 1M-follower account would enqueue hundreds of millions of items.

```python
class CrawlBudget:
    """
    Enforces hard limits on crawl scope.
    Checked before each enqueue operation.
    """
    def __init__(self, job: CrawlJob):
        self.max_accounts = job.max_accounts
        self.max_depth = job.depth

    async def can_enqueue(self, depth: int, current_count: int) -> bool:
        if depth > self.max_depth:
            return False
        if current_count >= self.max_accounts:
            return False
        return True
```

Additionally: accounts already in the database with `scraped_at` within the last 24 hours are **not** re-scraped — they are used as-is for graph construction. This dramatically reduces redundant scraping.

---

## 11. Cross-Platform Detection — Full Patterns

```python
# scraper/extractors/cross_platform.py

PLATFORM_PATTERNS: dict[str, list[tuple[str, float]]] = {
    # (pattern, confidence)
    "instagram": [
        (r"instagram\.com/(?:@)?([\w.]+)/?", 1.0),
        (r"instagr\.am/(?:@)?([\w.]+)/?", 1.0),
        (r"(?:ig|insta):\s*@?([\w.]+)", 0.85),
        (r"(?:ig|instagram)\s*[:|->@]\s*@?([\w.]+)", 0.85),
        (r"@([\w.]{3,30})\s+(?:on\s+)?(?:ig|insta|instagram)\b", 0.75),
    ],
    "github": [
        (r"github\.com/([\w-]+)(?:/[\w-]+)?", 1.0),
        (r"gh:\s*([\w-]+)", 0.85),
        (r"github:\s*([\w-]+)", 0.85),
    ],
    "linkedin": [
        (r"linkedin\.com/in/([\w%-]+)/?", 1.0),
        (r"linkedin\.com/pub/([\w%-]+)/?", 1.0),
        (r"linkedin:\s*([\w%-]+)", 0.8),
        (r"li(?:nkedin)?\.com/in/([\w%-]+)", 1.0),
    ],
    "tiktok": [
        (r"tiktok\.com/@([\w.]+)/?", 1.0),
        (r"(?:tt|tiktok):\s*@?([\w.]+)", 0.85),
        (r"@([\w.]+)\s+on\s+tiktok\b", 0.75),
    ],
    "youtube": [
        (r"youtube\.com/@([\w-]+)/?", 1.0),
        (r"youtube\.com/(?:c/|channel/|user/)([\w-]+)/?", 1.0),
        (r"youtu\.be/channel/([\w-]+)/?", 0.9),
    ],
    "telegram": [
        (r"t\.me/([\w]+)", 1.0),
        (r"telegram\.(?:me|org)/(@?[\w]+)", 1.0),
        (r"tg:\s*@?([\w]+)", 0.85),
    ],
    "discord": [
        (r"discord\.gg/([\w-]+)", 1.0),
        (r"discord\.com/invite/([\w-]+)", 1.0),
        # Discord handles (username#discriminator or new username) are not reliably detectable in bio text
    ],
    "substack": [
        (r"([\w-]+)\.substack\.com", 1.0),
        (r"substack\.com/@([\w-]+)", 1.0),
    ],
}

# URL normalization per platform
HANDLE_NORMALIZERS: dict[str, Callable[[str], str]] = {
    "instagram": lambda h: h.lower().strip("@/"),
    "github": lambda h: h.lower().strip("/"),
    "linkedin": lambda h: unquote(h).lower().strip("/"),
    "tiktok": lambda h: h.lower().strip("@/"),
    "youtube": lambda h: h.lower().strip("@/"),
}

def detect_all(text: str, source_field: str) -> list[PlatformHandle]:
    results = []
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern, confidence in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                handle = match.group(1)
                normalizer = HANDLE_NORMALIZERS.get(platform, str.lower)
                results.append(PlatformHandle(
                    platform=platform,
                    handle=normalizer(handle),
                    raw_match=match.group(0),
                    confidence=confidence,
                    source=source_field,
                ))
    # Deduplicate by (platform, handle), keep highest confidence
    return _deduplicate(results)
```

---

## 12. Dependency Graph

Which modules depend on which. An arrow means "imports from".

```
scraper/browser     -> config/settings
scraper/proxy       -> config/settings, storage/models/proxy
scraper/ratelimit   -> config/settings
scraper/extractors  -> scraper/browser, scraper/ratelimit
scraper/jobs        -> scraper/extractors, scraper/proxy, storage/repositories, graph/builder

graph/backends      -> config/settings
graph/builder       -> graph/backends, storage/repositories
graph/algorithms    -> graph/backends

storage/models      -> storage/base
storage/repositories -> storage/models, storage/session
storage/engine      -> config/settings

api/routers         -> storage/repositories, graph/backends, scraper/jobs
api/main            -> api/routers, scraper/jobs/runner, storage/engine, graph/backends

cli/commands        -> api (HTTP client) OR storage/repositories + graph/backends (direct mode)

frontend            -> api (HTTP)
```

**Modules that can be developed independently (no internal deps):**

- `storage/` — standalone, only depends on SQLAlchemy
- `graph/backends/` — standalone, only depends on Neo4j driver or networkx
- `config/` — standalone, only depends on pydantic-settings
- `frontend/` — standalone, only depends on the HTTP API contract

**Development order recommendation:**

1. `config/` + `storage/` — foundation
2. `graph/backends/` — graph layer
3. `scraper/proxy/` + `scraper/ratelimit/` — scraper support
4. `scraper/browser/` + `scraper/extractors/` — scraper core
5. `scraper/jobs/` — job orchestration
6. `graph/builder/` — ingestor
7. `api/` — HTTP layer
8. `cli/` — CLI layer
9. `frontend/` — UI

---

## 13. Development Environment

### 13.1 Local Dev Without Docker

Minimum viable local setup (no external services):

```bash
# 1. Clone and install
git clone https://github.com/org/osint-twitter
cd osint-twitter
py -3.10 -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/Mac

py -3.10 -m pip install -e ".[dev]"

# 2. Install Playwright browsers
py -3.10 -m playwright install chromium

# 3. Configure
cp .env.example .env
# Edit .env: DATABASE_URL defaults to SQLite, GRAPH_BACKEND defaults to networkx
# No external services needed

# 4. Run migrations
alembic upgrade head

# 5. Start API
py -3.10 -m uvicorn api.main:app --reload --port 8000

# 6. Start frontend (separate terminal)
cd frontend
npm install
npm run dev  # Vite dev server on port 5173

# 7. Use CLI
py -3.10 -m osint crawl start @someuser --depth 2
```

### 13.2 Docker Compose — Full Stack

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    environment:
      DATABASE_URL: sqlite+aiosqlite:////app/data/osint.db
      GRAPH_BACKEND: networkx
    depends_on:
      - db-init

  db-init:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    command: alembic upgrade head
    volumes:
      - ./data:/app/data
    environment:
      DATABASE_URL: sqlite+aiosqlite:////app/data/osint.db

  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "5173:80"

  # Optional: Neo4j stack
  # Use: docker-compose -f docker-compose.yml -f docker-compose.neo4j.yml up
```

```yaml
# docker-compose.neo4j.yml
version: "3.9"

services:
  neo4j:
    image: neo4j:5.18-community
    ports:
      - "7474:7474"   # Browser UI
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      NEO4J_dbms_memory_heap_initial__size: 512m
      NEO4J_dbms_memory_heap_max__size: 2G
      NEO4J_dbms_memory_pagecache_size: 512m
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  api:
    environment:
      GRAPH_BACKEND: neo4j
      NEO4J_URL: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: password

volumes:
  neo4j_data:
  neo4j_logs:
```

### 13.3 Python Dependencies (`pyproject.toml`)

```toml
[project]
name = "osint-twitter"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    # Scraping
    "playwright>=1.44",
    "fake-useragent>=1.5",

    # Storage
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "asyncpg>=0.29",        # Postgres
    "alembic>=1.13",

    # Graph
    "networkx>=3.3",
    "neo4j>=5.20",          # Neo4j Python driver
    "python-louvain>=0.16", # Community detection for networkx

    # API
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",

    # CLI
    "click>=8.1",
    "rich>=13.7",            # Table/color output

    # Utilities
    "httpx>=0.27",           # Async HTTP (proxy health checks, cross-platform fetches)
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-playwright>=0.5",
    "ruff>=0.4",             # Linter + formatter
    "mypy>=1.10",
]

[project.scripts]
osint = "cli.main:cli"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## 14. Risks and Mitigations

### 14.1 Anti-Bot Countermeasures

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| IP ban | Repeated requests from same IP | Proxy rotation per session; conservative rate profile default |
| Browser fingerprinting | Headless Chromium detected via JS properties | `playwright-stealth` library patches `navigator.webdriver`, WebGL noise, etc. |
| Behavioral analysis | Request timing patterns too uniform | Gaussian delay distribution, variable scroll patterns |
| CAPTCHA challenges | Cloudflare Turnstile / Google reCAPTCHA | Detect CAPTCHA page, pause job, surface to user via SSE event for manual intervention |
| Account requirement wall | X demanding login for certain content | Session management with optional pre-authenticated cookies; graceful degradation to public-only data |
| DOM changes | X changes selectors without notice | `SELECTOR_REGISTRY` with versioning; automated selector validation tests; GitHub issue template for selector breakage reports |
| Rate limit page | HTTP 429 or redirect to error page | `detect_rate_limit_page()` check after every navigation; exponential backoff; proxy rotation on rate limit hit |

**`playwright-stealth`:** Install via `py -3.10 -m pip install playwright-stealth`. Apply to every new browser context:

```python
from playwright_stealth import stealth_async
await stealth_async(page)
```

### 14.2 Data Storage Limits

| Scenario | Storage Impact | Mitigation |
|----------|---------------|-----------|
| Deep crawl (depth 3, 10K accounts) | ~500MB SQLite | WAL mode, periodic VACUUM |
| Very deep crawl (depth 4, 100K accounts) | ~5GB SQLite | Postgres migration path documented |
| Raw blob accumulation | Unbounded growth | `MAX_RAW_DATA_AGE_DAYS` config purges old blobs; raw data is supplementary to ORM models |
| Graph in networkx RAM | 100K nodes = ~1-2GB RAM | Neo4j swap path; `GRAPH_BACKEND=neo4j` config |
| Graph in Neo4j | Scales to tens of millions of nodes | Per-job graph namespace isolation; periodic `DETACH DELETE` of orphaned nodes |

### 14.3 Graph Scalability

The transition point from networkx to Neo4j:

- **<10K nodes:** networkx is fine, simpler, no external service
- **10K-500K nodes:** Neo4j community, single instance, 4-8GB RAM allocation
- **>500K nodes:** Neo4j community + GDS plugin for algorithms; consider Neo4j AuraDB Free tier for hosted
- **>5M nodes:** Neo4j Enterprise or migration to a purpose-built graph platform (TigerGraph, MemGraph)

### 14.4 Selector Versioning Risk

X's DOM is the highest-risk single dependency. Mitigation strategy:

1. `SELECTOR_REGISTRY` is version-keyed
2. A dedicated `tests/test_selectors.py` runs against saved HTML snapshots (committed to repo) to detect breakage without live scraping
3. A `scripts/validate_selectors.py` script can be run against live X to verify current selectors work — run this manually before major releases
4. `extractor_version` and `selector_version` are recorded on every `RawScrapeResult` — helps diagnose when scraper breakage occurred

### 14.5 Legal and Ethical Considerations

This is an open-source tool. The architecture is designed to:
- Operate locally only (no data sent to third parties)
- Respect rate limits and human-like delay profiles
- Not store authentication credentials in plaintext in a committed file
- Provide depth limits to prevent runaway scraping

Include `DISCLAIMER.md` in the repo stating this tool is for authorized OSINT research. Users are responsible for compliance with X's Terms of Service and applicable laws.

---

## 15. Technical Tradeoffs — Decision Log

| Decision | Chosen | Alternative Considered | Reasoning |
|----------|--------|----------------------|-----------|
| Architecture pattern | Modular monolith | Microservices | Team size / contributor onboarding. Extraction path preserved via module boundaries. |
| Scraper engine | Playwright | requests + parsel, Selenium | Playwright handles JS rendering, has async-native API, better fingerprint control than Selenium |
| Graph backend (default) | networkx | Neo4j default | Zero external dependencies. Lowers contributor barrier. Neo4j opt-in via docker-compose overlay. |
| Job queue | SQLite-backed | Celery + Redis | No external broker dependency. SQLite WAL handles local concurrency. Swap path to Redis/Celery documented. |
| Frontend visualization | Cytoscape.js | D3.js, Sigma.js | Purpose-built for graphs. Better default layouts. Lower contributor friction. Sigma.js considered for >5K node WebGL path. |
| State management | Zustand | Redux, Jotai | Minimal boilerplate, async-friendly, small bundle. Redux adds complexity that isn't justified here. |
| ORM | SQLAlchemy async | Tortoise ORM, SQLModel | SQLAlchemy is the standard. Mature async support. Alembic integration. SQLModel considered but adds Pydantic coupling. |
| API framework | FastAPI | Flask, Django REST | Native async, Pydantic integration, automatic OpenAPI docs. Flask requires more plumbing. |
| Frontend build | Vite | Create React App, Webpack | Significantly faster HMR. Native ES modules. CRA is deprecated. |
| Python version | 3.10 | 3.11, 3.12 | Explicit project constraint from CLAUDE.md. 3.10 is the pinned version. |

### What Was Intentionally Deferred

- **Authentication/multi-user:** Not needed for single-operator local tool
- **Celery/Redis job broker:** Deferred until multi-machine use case emerges
- **GraphQL API:** REST is sufficient, less complexity for contributors
- **Distributed scraping:** Single-machine Playwright pool covers the use case
- **ML-based account deduplication:** Confidence scoring via regex patterns is sufficient for v1; NLP-based entity resolution is a v2 feature
- **WebGL graph renderer:** Cytoscape.js handles up to ~5K nodes acceptably; WebGL renderer deferred until user feedback establishes it as a real pain point

---

## 16. Future Expansion Strategy

### Extraction Path to Microservices

If the tool evolves into a hosted SaaS:

| Module | Extraction trigger | Target service |
|--------|--------------------|----------------|
| `scraper/` | Multi-machine scraping need | Scraper Worker Service (Celery workers) |
| `graph/` | Shared graph across users | Graph Service (standalone Neo4j + API) |
| `storage/` | Multi-user data isolation | Database Service (Postgres, connection pooling via PgBouncer) |
| `api/` | Traffic beyond single process | API Gateway + multiple uvicorn workers behind nginx |

### Extensibility Points Built In

1. **New platform extractors:** Implement `AbstractExtractor`, register in `ExtractorRegistry`. Zero changes to job runner, graph builder, or API.

2. **New relationship types:** Add to `edges.py` schema, add corresponding enum value in `Relationship.rel_type`. Alembic migration for the column, new Cypher relationship type.

3. **New graph algorithms:** Add to `graph/algorithms/`. Expose via new `GET /api/v1/graph/{algorithm_name}` endpoint.

4. **New export formats:** Add formatter to `cli/formatters/` and corresponding route in `api/routers/export.py`.

5. **New proxy sources:** Implement `ProxySourceAdapter` interface in `scraper/proxy/loader.py`.

6. **Selector hot-reload:** The `SELECTOR_REGISTRY` can be loaded from an external JSON file (e.g., `config/selectors.json`) rather than hardcoded — enables community-maintained selector updates without code changes.

---

## Appendix A: File-Level Implementation Priority Map

For the first implementation sprint, build in this order:

**Sprint 1 — Core foundation (1-2 weeks):**
- `config/settings.py`
- `storage/base.py`, `storage/engine.py`, `storage/session.py`
- `storage/models/account.py`, `job.py`, `relationship.py`, `raw_data.py`
- `storage/repositories/account_repo.py`, `job_repo.py`
- Alembic setup + initial migration
- `tests/test_storage.py`

**Sprint 2 — Graph layer (1 week):**
- `graph/backends/base.py`
- `graph/backends/networkx_backend.py`
- `graph/schema/nodes.py`, `edges.py`
- `tests/test_graph_networkx.py`

**Sprint 3 — Scraper core (2-3 weeks):**
- `scraper/proxy/loader.py`, `health.py`, `rotator.py`
- `scraper/ratelimit/token_bucket.py`, `profiles.py`, `backoff.py`
- `scraper/browser/pool.py`, `session.py`, `fingerprint.py`, `page_utils.py`
- `scraper/extractors/base.py`, `twitter.py`, `cross_platform.py`
- `tests/test_extractors.py` (against saved HTML snapshots)

**Sprint 4 — Job system + ingestor (1 week):**
- `scraper/jobs/queue.py`, `runner.py`
- `graph/builder/ingestor.py`

**Sprint 5 — API + CLI (1 week):**
- `api/main.py`, all routers, schemas
- `cli/main.py`, all command groups

**Sprint 6 — Frontend (2 weeks):**
- React app scaffold (Vite + TypeScript + Tailwind)
- Cytoscape.js graph canvas
- Job panel + SSE integration
- Account detail drawer

---

`D:\random_tools\twitter-osint\` — all implementation should land here, following the directory structure defined in section 2.
