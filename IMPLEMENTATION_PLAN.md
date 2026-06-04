# TwitterOSINT — Executable Implementation Plan

Build sequence derived from `ARCHITECTURE.md`. Architecture defines WHAT (modules, models, interfaces); this plan defines ORDER, per-task file list, tests, definitions of done, risk sequencing, effort. All paths absolute under `D:\random_tools\twitter-osint\`.

## Guiding principles

- **Python invocation always `py -3.10`** (never bare `python`/`pip`). Inside venv, prefer `py -3.10 -m <tool>`.
- **TDD where logic is pure** (regex, backoff math, token bucket, repositories against in-memory SQLite, networkx ops, API routes with mocked scraper). Live scraping NOT unit-tested.
- **De-risk scraper first by decoupling from live DOM** — build extractors against committed saved-HTML snapshots before wiring into job runner (architecture §14.4).
- **Walking skeleton early** — thin vertical slice (scrape one profile from saved HTML → store → graph node → API → CLI) demoable by end of scraper-core phase.
- **Module independence (§12):** `storage/`, `graph/backends/`, `config/`, `frontend/` have no internal cross-deps; build in parallel.

---

## Phase 0 — Project Bootstrap (sequential, blocks everything)

**Goal:** Clonable repo with toolchain, scaffold, green "hello" test run.

**Tasks (in order):**

1. `git init`. Default branch `main`.
2. `.gitignore`: MUST include `config/proxies.txt`, `config/sessions/`, `config/cookies.json`, `.env`, `data/`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.pkl`, `frontend/node_modules/`, `frontend/dist/`. Add committed `config/sessions/.gitkeep`.
3. Directory scaffold matching architecture §2. Every Python package dir gets `__init__.py`:
   - `scraper/` with `browser/ extractors/ proxy/ ratelimit/ jobs/`
   - `graph/` with `backends/ schema/ algorithms/ builder/`
   - `storage/` with `models/ repositories/ migrations/`
   - `api/` with `routers/ schemas/ dependencies/`
   - `cli/` with `commands/ formatters/`
   - `config/`, `tests/` (mirror module structure), `docker/`, `frontend/` (scaffolded later)
4. `pyproject.toml` from architecture §13.3 verbatim (+ `[tool.mypy]` py310 `ignore_missing_imports=true`, `[tool.ruff.lint]`).
5. `.env.example` mirroring every `Settings` field (§9.1), placeholder defaults + comments. Committed.
6. `config/ua_pool.txt` (seed small, expand to 300+ later), committed `config/proxies.txt.example`.
7. `DISCLAIMER.md` (§14.5), minimal `README.md` (§13.1 quickstart), MIT `LICENSE`.
8. `py -3.10 -m venv .venv`, activate (`.venv\Scripts\Activate.ps1`), `py -3.10 -m pip install -e ".[dev]"`.
9. `py -3.10 -m playwright install chromium`.
10. `tests/test_smoke.py` (`assert True`) — proves pytest + `asyncio_mode=auto`.

**Tests:** `pytest` green; `ruff check .` + `mypy .` clean.

**DoD:** Fresh checkout + §13.1 steps succeed on Windows/PowerShell; pytest/ruff/mypy pass; gitignored files confirmed not tracked.

**Effort:** 0.5 day. **Sequencing:** Strictly first; blocks all.

---

## Phase 1 — Config + Storage (foundation; partially parallelizable)

**Depends on:** Phase 0. Maps to Sprint 1. `config/` + `storage/` parallel (config no deps; storage/engine depends on config but stub `Settings` early).

### 1a. config/
- `config/settings.py` — full `Settings` Pydantic model (§9.1).
- Notes: pydantic-settings v2 `SettingsConfigDict(env_file=".env")`. `DATA_DIR`/`SESSION_DIR` relative defaults — resolve absolute at use. Cached `get_settings()` (`functools.lru_cache`).
- Tests `tests/test_config.py`: defaults load; `.env` override (`monkeypatch.setenv`); `GRAPH_BACKEND` rejects bad literals; `BROWSER_POOL_SIZE` bounds.
- DoD: `get_settings()` returns valid `Settings`; invalid env raises.

### 1b. storage/
**Files (order):**
1. `storage/base.py` — SQLAlchemy `DeclarativeBase`.
2. `storage/models/` — account, relationship, platform (CrossPlatformLink), job (CrawlJob), raw_data (RawScrapeResult), JobQueueItem, ProxyRecord (§4.1). JSON cols: `postgresql.JSONB().with_variant(sqlite.JSON(), "sqlite")`. All enums.
3. `storage/engine.py` — `create_engine_from_settings()` + SQLite WAL `@event.listens_for(..., "connect")` (`PRAGMA journal_mode=WAL; synchronous=NORMAL`).
4. `storage/session.py` — async session factory (`async_sessionmaker`, `expire_on_commit=False`).
5. `storage/repositories/` — account_repo, job_repo, relationship_repo (§6.2). account_repo: upsert, bulk_upsert, get_by_username, get_by_depth, search, count. job_repo: CRUD + get_events_since + queue claim helpers.
6. Alembic: `alembic init storage/migrations`, edit `env.py` import `Base`, read `DATABASE_URL`; initial migration `--autogenerate`. All indexes §4.1. Real `downgrade()`.

**Gotchas:** All sessions async. **Alembic autogenerate runs sync** — `env.py` must handle async URL (swap `sqlite+aiosqlite`→`sqlite`, or `connection.run_sync`) — classic async-Alembic gotcha. Unique relationship index `(source, target, rel_type)` underpins upsert-or-increment for MENTIONS/REPLIES.

**Tests `tests/test_storage.py`:** repos against in-memory SQLite (`:memory:`); upsert idempotency, bulk_upsert count, unique-constraint dedupe, get_by_depth, search, JSON round-trip; `alembic upgrade head`→`downgrade base` round-trip on temp file DB.

**DoD:** `alembic upgrade head` builds full schema on SQLite; repo tests green; WAL confirmed (`PRAGMA journal_mode`).

**Effort:** 2-3 days. Foundation for graph/builder, jobs, api.

---

## Phase 2 — Graph Backends + Schema (parallelizable with Phase 3)

**Depends on:** config/. Independent of storage. Maps to Sprint 2.

**Files (order):**
1. `graph/backends/base.py` — `AbstractGraphBackend` + `GraphData`/`NodeData`/`EdgeData` TypedDicts.
2. `graph/schema/nodes.py`, `edges.py` — type constants + node_id convention `"platform:@handle"`.
3. `graph/backends/networkx_backend.py` — `MultiDiGraph`, full interface; `run_cypher` raises NotImplementedError; pickle (dev) + graphml (export) persistence.
4. `graph/backends/neo4j_backend.py` — same interface, neo4j async driver; constraints/indexes §4.2. **Deferrable** (opt-in) — stub, prioritize networkx.
5. `graph/algorithms/traversal.py` (BFS/DFS depth+visit limits), then centrality, community (python-louvain), similarity (Jaccard). Traversal needed for subgraph endpoint; rest after skeleton.

**Gotchas:** networkx wraps sync in `async def` (or `asyncio.to_thread` for heavy). **networkx is process-local in-memory — API + JobRunner share one process (runner is `asyncio.create_task` in `api/main.py`), share the graph instance. CLI `--direct` gets separate instance from persisted file.** Document this. `get_subgraph(depth, limit)` enforces limit.

**Tests `tests/test_graph_networkx.py`:** upsert idempotency, neighbors by rel_type, subgraph depth/limit, counts, BFS depth cap, Jaccard, graphml/pickle round-trip. Offline.

**DoD:** networkx passes full contract; subgraph+traversal respect depth+limit; export round-trips. Neo4j passes same contract against docker Neo4j or marked skip/xfail.

**Effort:** 2-3 days (networkx) +1-2 Neo4j (deferrable). Parallel with Phase 3.

---

## Phase 3 — Scraper Support: proxy + ratelimit (parallelizable, pure logic)

**Depends on:** config/ (+ storage ProxyRecord). Highly unit-testable, good early-parallel workstream.

**Files (order):**
1. `scraper/proxy/models.py` — `Proxy` + `ProxyHealth` (latency_ms, success_rate rolling, last_checked_at, is_alive).
2. `scraper/proxy/loader.py` — load_from_file (4 formats, skip malformed+warn), fetch_free_proxies (proxyscrape.com v3 via httpx), get_all.
3. `scraper/proxy/health.py` — async check/check_all vs TEST_URLS via httpx; filter dead.
4. `scraper/proxy/rotator.py` — weighted-random by health; mark_failed/success; fallback to direct (`next()`→None) on exhaustion + warning.
5. `scraper/ratelimit/backoff.py` — full-jitter exponential.
6. `scraper/ratelimit/token_bucket.py` — async-safe per-domain; consume blocks.
7. `scraper/ratelimit/profiles.py` — conservative/moderate/aggressive (§3.1.3).

**Gotchas:** Token bucket async-safe (`asyncio.Lock` + monotonic clock); test with fake clock (no real sleeps). Backoff `random.uniform(0, min(max_wait, base**attempt))` — seed RNG, assert bounds. Mock httpx for proxyscrape.

**Tests:** `tests/test_proxy.py` (4 formats, malformed skip, rotator dead-exclude+fallback, health mocked httpx), `tests/test_ratelimit.py` (bucket refill fake clock, backoff bounds+growth+jitter, profile values).

**DoD:** proxy + ratelimit fully unit-tested offline, no live network, no real sleeps.

**Effort:** 2 days. Parallel with Phases 1/2.

---

## Phase 4 — Scraper Core: browser + extractors (HIGHEST RISK — de-risk via snapshots)

**Depends on:** browser on config+ratelimit; extractors on browser+ratelimit. Rest of Sprint 3.

**Risk-ordered (critical):** X live DOM = single highest-risk dep (§14.4). Build/validate against **committed saved-HTML snapshots first**, before live browser or job-runner wiring.

**Order:**
1. `scraper/extractors/base.py` — `AbstractExtractor` + RawProfile/RawConnections/RawTweet/RawInteraction TypedDicts.
2. `scraper/extractors/cross_platform.py` — PLATFORM_PATTERNS, HANDLE_NORMALIZERS, detect_all, normalize_handle, _deduplicate (§3.1.4 + §11). **Pure regex — fully testable zero scraping. Build + fully test FIRST. Easiest high-value win.**
3. **Capture snapshots:** manually save real X profile/timeline HTML into `tests/fixtures/snapshots/` (`twitter_profile_v1.html`, `twitter_timeline_v1.html`). Commit. Drives test_selectors + test_extractors.
4. `scraper/extractors/twitter.py` — SELECTOR_REGISTRY (versioned), extract_profile/following/followers/tweets/mentions/interactions, _infinite_scroll_collect, _handle_age_gate, _detect_rate_limit_page. **Make selector application a pure function over parsed HTML/DOM** (accept content/tree) → runs against snapshots without live browser. Live `page` path = thin wrapper.
5. `scripts/validate_selectors.py` — manual live-only, verify selectors vs real X before releases. Not in CI.
6. `scraper/browser/`: fingerprint.py, page_utils.py (human_scroll/delay/click via `random.gauss`), session.py (load/save `config/sessions/{identity}.json`), pool.py (BrowserPool checkout/checkin/shutdown, rotate after N pages). Apply `playwright-stealth` per context. **FLAG: add `playwright-stealth` to pyproject deps.**
7. Stub extractors: instagram, github, tiktok, linkedin (stub). Not on skeleton path.

**Gotchas:** Keep selector logic separate from navigation so tests skip Playwright. `_detect_rate_limit_page`/`_handle_age_gate` — clear return contracts (runner depends on them for backoff/pause). Infinite scroll has limit; test loop/termination with fake page.

**Tests:**
- `tests/test_cross_platform.py` — exhaustive regex per platform, confidence (1.0 URL / 0.7-0.85 bio), normalization, dedupe. Offline.
- `tests/test_selectors.py` — SELECTOR_REGISTRY["v1"] vs snapshots; detects breakage no live scraping (§14.4). Fixtures.
- `tests/test_extractors.py` — extract_profile/tweets vs snapshots → expected RawProfile/RawTweet. Fixtures.
- Browser pool / live nav: manual/live-only, not CI. Optional `@pytest.mark.live`, skipped default.

**DoD:** cross_platform + selector + extractor tests green vs snapshots offline; validate_selectors.py runs manually vs live X; browser pool launches stealth Chromium, fetches one page manually.

**Effort:** 4-6 days (largest, riskiest). Must follow Phase 3 + config; cross_platform sub-task anytime.

---

## MILESTONE — Walking Skeleton (earliest end-to-end proof)

**Insert immediately after Phase 4 extractor-against-snapshot works, before full job system.** Minimal pipeline proving architecture end-to-end:

> Parse committed snapshot HTML → `TwitterExtractor.extract_profile` → RawProfile → `account_repo.upsert` writes SQLite → thin `graph/builder/ingestor` upserts one node into networkx → `GET /api/v1/accounts/{id}` returns it → `osint account get <username> --direct` prints via table formatter.

Requires minimal slices of Phase 5 (tiny ingestor), 6 (one router + main.py), 7 (one CLI direct command) pulled forward. **Most important sequencing decision: surfaces interface mismatches (TypedDict ↔ ORM ↔ GraphData) at day ~8 instead of day ~25.**

**DoD:** One command, no live network, produces stored account + graph node + API/CLI readout.

---

## Phase 5 — Job System + Full Ingestor

**Depends on:** extractors, proxy, storage repos, graph builder (§12). Sprint 4.

**Files (order):**
1. `graph/builder/ingestor.py` — full: RawProfile/RawConnections/RawTweet → account_repo upserts + graph node/edge upserts + CrossPlatformLink rows. MENTIONS/REPLIES count-increment via unique relationship index.
2. `scraper/jobs/queue.py` — JobQueue (enqueue, claim_next atomic optimistic update, complete, fail-with-retry, requeue_stale). SQLite: serialize claims via `BEGIN IMMEDIATE`/WAL (§10.2).
3. `scraper/jobs/runner.py` — JobRunner spawning N worker coroutines (one per pool slot), _process_item 7-step flow (§10.3), CrawlBudget depth/count guard (§10.4), 24h freshness skip, SSE event emission.

**Gotchas:** `claim_next` correctness under WAL is the crux — test optimistic claim prevents double-processing concurrent workers. **FLAG: SSE polls get_events_since every 1s. Add lightweight `job_event(id, job_id, sequence, type, payload, created_at)` table + migration — architecture implies via get_events_since but doesn't define model.** CrawlBudget checked before every enqueue; 24h freshness avoids re-scrape.

**Tests:** `tests/test_jobs.py` (offline) — enqueue/claim/complete/fail+retry/requeue_stale vs in-memory SQLite; concurrent-claim no-double-process; CrawlBudget boundaries; freshness skip. `tests/test_ingestor.py` — canned RawProfile/RawConnections → correct accounts/relationships/links + graph nodes/edges, MENTIONS increment on repeat.

**DoD:** Job enqueued, worker (extractor fed by stubbed/snapshot browser, not live) drains queue, stores accounts+relationships, builds graph, respects depth/budget, emits events — all offline + tested.

**Effort:** 3-4 days. Must follow Phases 1, 2, 4.

---

## Phase 6 — API Layer

**Depends on:** storage repos, graph backends, scraper/jobs (§12). Sprint 5.

**Files (order):**
1. `api/dependencies/` — get_db (async session), get_graph (backend instance), optional X-API-Key check.
2. `api/schemas/` — CreateJobRequest, JobResponse/JobDetailResponse, AccountResponse/AccountDetailResponse, RelationshipResponse, CrossPlatformLinkResponse, GraphData, JobProgressEvent.
3. `api/routers/`: health.py (live/ready/stats) first. Then accounts, graph, jobs (incl SSE /events), scrape, export (csv/json/graphml/cytoscape-json), config.
4. `api/main.py` — app factory: include routers, on-startup create engine + graph backend + JobRunner via `asyncio.create_task` (§10.3), on-shutdown stop runner gracefully.

**Gotchas:** All handlers `async def`; long work dispatched to queue, never in handler. SSE pattern §5.3 (StreamingResponse, text/event-stream, poll get_events_since). Export graph.json = Cytoscape.js-shaped. **JobRunner same-process → in-memory networkx shared with handlers (consistent reads). Single uvicorn worker for networkx; multi-worker only with Neo4j.**

**Tests `tests/test_api.py`:** FastAPI TestClient/httpx.AsyncClient vs app wired to in-memory SQLite + networkx, **scraper/job runner mocked**. Create job returns immediately + enqueues; accounts/graph/export routes; health/ready; API-key gate on/off; SSE emits frame. Offline.

**DoD:** `uvicorn api.main:app` starts; `/health/ready` 200 with SQLite+networkx; all routes covered with mocked scraper; OpenAPI at `/docs`.

**Effort:** 3-4 days. After Phases 1, 2, 5.

---

## Phase 7 — CLI Layer

**Depends on:** api (HTTP client) OR storage+graph (direct mode) (§12). Sprint 5.

**Files (order):**
1. `cli/formatters/` — TableFormatter (rich), JSONFormatter, CSVFormatter, GraphMLFormatter. Default by `sys.stdout.isatty()` (§8.2).
2. `cli/main.py` — root group `--api-url`, `--direct`, `--output`; exposes `cli` (the entrypoint).
3. `cli/commands/`: crawl, account, graph, export, config (full tree §8.1). Each works API mode (httpx) + direct mode (import repos/backends).

**Gotchas:** Direct mode loads own graph from persisted pickle/graphml — document consistency caveat. `config proxy refresh` re-fetches proxyscrape; `config session list/clear` touches `config/sessions/`.

**Tests `tests/test_cli.py`:** Click CliRunner; direct mode vs in-memory SQLite + networkx; table/json/csv shapes. API mode mocked httpx.

**DoD:** `py -3.10 -m osint account get <user> --direct` + API-mode equivalent both work; all groups invokable; valid JSON/CSV/graphml.

**Effort:** 2-3 days. After Phase 6 (API mode); direct mode after Phases 1+2.

---

## Phase 8 — Frontend (fully parallelizable from day 1 against API contract)

**Depends on:** only HTTP API contract (§12) — build parallel with entire backend using mock server, then point at real API.

**Tasks (order):**
1. Scaffold `frontend/`: Vite + React + TS + Tailwind (`npm create vite@latest`). `vite.config.ts` proxy `/api`→`http://localhost:8000` (§7.5).
2. `frontend/src/lib/` — API client + Cytoscape.js config; install cytoscape, react-cytoscapejs, zustand.
3. `frontend/src/stores/graphStore.ts`, `jobStore.ts` (§7.3).
4. `frontend/src/hooks/useJobEvents.ts` — EventSource SSE consumer, incremental `cy.add()` merge (§7.4).
5. Components (§7.2): Layout → Sidebar (JobPanel/NewJobForm/JobList, FilterPanel, ExportPanel), MainCanvas (GraphCanvas, tooltips, GraphControls), AccountDetailDrawer, StatusBar.

**Gotchas:** Incremental via `cy.add()`, never full re-render (§7.4). node_id `platform:@handle` must match backend. Cytoscape OK to ~5K nodes; WebGL deferred.

**Tests:** Vitest stores + SSE hook (mock EventSource); manual E2E vs running API.

**DoD:** `npm run dev` serves UI; create job hits API, SSE streams progress, nodes/edges render incrementally + clickable, export downloads.

**Effort:** 5-7 days. Parallel throughout; final integration after Phase 6.

---

## Phase 9 — Docker, Docs, Hardening (finalization)

**Files:** `docker/Dockerfile.api`, `docker/Dockerfile.frontend`, `docker-compose.yml`, `docker-compose.neo4j.yml` (§13.2). Flesh out stub extractors. VACUUM/raw-blob purge for MAX_RAW_DATA_AGE_DAYS. GitHub issue template for selector breakage. Expand ua_pool.txt to 300+.

**DoD:** `docker-compose up` brings up api+frontend (networkx); `-f docker-compose.neo4j.yml` overlay brings up Neo4j + switches backend; README quickstart verified on fresh clone.

**Effort:** 2-3 days.

---

## Testing Strategy (consolidated)

**Unit-testable offline (bulk — TDD):**
- Cross-platform regex + normalization + dedupe (`test_cross_platform.py`).
- Backoff math, token bucket (fake clock), profiles (`test_ratelimit.py`).
- Proxy parse/health(mocked httpx)/rotation+fallback (`test_proxy.py`).
- Repos vs in-memory SQLite; Alembic up/down (`test_storage.py`, `test_config.py`).
- networkx backend + traversal/similarity (`test_graph_networkx.py`).
- Ingestor mapping + job queue concurrency/budget/freshness (`test_ingestor.py`, `test_jobs.py`).
- API routes via TestClient, **mocked scraper/job runner** (`test_api.py`).
- CLI via CliRunner, direct + mocked-httpx API mode (`test_cli.py`).

**Needs saved-HTML-snapshot fixtures (`tests/fixtures/snapshots/`):**
- Selector validation `test_selectors.py` — SELECTOR_REGISTRY vs committed HTML, no live scraping (§14.4).
- Extractor output `test_extractors.py` — full RawProfile/RawTweet from snapshots.

**Manual / live-only (NOT CI):**
- Real Playwright scraping vs X (browser pool, age gate, rate-limit detection, infinite scroll).
- `scripts/validate_selectors.py` vs live X before releases.
- Full UI E2E vs running API.

**CI gate:** `ruff check` + `mypy` + `pytest` (offline + snapshot). Mark live `@pytest.mark.live`, exclude default.

---

## Parallelization & Sequencing Summary

| Phase | Effort | Depends on | Parallel with |
|---|---|---|---|
| 0 Bootstrap | 0.5d | — | nothing (blocks all) |
| 1 config+storage | 2-3d | 0 | 2, 3, 8 |
| 2 graph backends | 2-3d (+1-2 Neo4j) | 0 (config) | 1, 3, 8 |
| 3 proxy+ratelimit | 2d | 0 (config) | 1, 2, 8 |
| 4 browser+extractors | 4-6d | 3 (+config); cross_platform anytime | 8 |
| **Skeleton milestone** | (slice) | thin bits of 1,2,4,5,6,7 | — |
| 5 jobs+ingestor | 3-4d | 1,2,4 | 8 |
| 6 api | 3-4d | 1,2,5 | 8 |
| 7 cli | 2-3d | 6 (API mode); 1+2 (direct) | 8 |
| 8 frontend | 5-7d | API contract only | everything |
| 9 docker/docs | 2-3d | 6,7,8 | — |

**Critical path (sequential):** 0 → (1 ∥ 2 ∥ 3) → 4 → 5 → 6 → 7 → 9. **Fully parallel tracks (§12):** storage, graph/backends, config, frontend. Cross-platform regex (inside Phase 4) = early parallel win. Single-dev total ≈ 5-7 weeks; 2-3 parallel contributors → ~3-4 weeks.

---

## Open Decisions Flagged (recommended defaults)

1. **CLI entrypoint:** pyproject says `cli.main:cli` but §12 treats CLI as package. **Default:** `cli/main.py` exposing `cli`.
2. **playwright-stealth** referenced §14.1, absent from pyproject deps. **Default:** add to `[project] dependencies`.
3. **Job-event persistence for SSE:** get_events_since referenced, no JobEvent model in §4.1. **Default:** add `job_event(id, job_id, sequence, type, payload, created_at)` table + migration.
4. **Sessions gitignore:** §2 lists cookies.json; §3.1.1 uses `config/sessions/{identity}.json`. **Default:** gitignore whole `config/sessions/` + `config/cookies.json`, commit `.gitkeep`.
5. **networkx single-process sharing:** API + JobRunner share in-process graph; CLI `--direct` loads separate persisted copy. **Default:** document caveat; force single uvicorn worker when `GRAPH_BACKEND=networkx`.
6. **Alembic async env.py:** autogenerate needs sync-driver path. **Default:** detect async URL in env.py, run via `connection.run_sync` (or sync URL alias).

---

## Critical Files
- `config/settings.py`
- `storage/models/account.py`
- `graph/backends/base.py`
- `scraper/extractors/twitter.py`
- `scraper/jobs/runner.py`
