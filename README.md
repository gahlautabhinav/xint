# xint — Twitter/X OSINT Network Mapper

> Open-source intelligence tool for mapping Twitter/X relationship networks. Given a seed username, builds a full graph of connected accounts via follows, mentions, replies, quote tweets, and cross-platform profile links.

> **Read [DISCLAIMER.md](DISCLAIMER.md) before use.** Scraping Twitter/X may violate their Terms of Service. You are solely responsible for legal compliance in your jurisdiction.

---

## What It Does

- **Network crawl** — follows/followers, mentions, replies, quote tweets up to configurable depth
- **Cross-platform detection** — detects Instagram, GitHub, LinkedIn, TikTok, YouTube, Telegram, Discord, Substack handles from bios and pinned tweets
- **Interactive graph UI** — React + Cytoscape.js visualization, click-to-expand nodes, filter by relationship type
- **REST API + CLI** — FastAPI backend, Click CLI (API mode and direct/offline mode)
- **Anti-detection** — Playwright (full browser, not requests), playwright-stealth, UA rotation, Gaussian human-like delays, pluggable proxy rotation
- **No official X API required** — scraping only, no API key needed

---

## Build Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0 — Bootstrap | ✅ Done | Repo scaffold, toolchain, green CI |
| Phase 1 — Config + Storage | 🔨 In progress | Pydantic settings, SQLAlchemy models, Alembic |
| Phase 2 — Graph Backends | ⏳ Planned | networkx (default) + Neo4j (opt-in) |
| Phase 3 — Proxy + Rate Limit | ⏳ Planned | Token bucket, backoff, proxy rotator |
| Phase 4 — Scraper Core | ⏳ Planned | Playwright browser pool, extractors, anti-detect |
| Phase 5 — Job System | ⏳ Planned | SQLite job queue, crawl runner, SSE events |
| Phase 6 — API | ⏳ Planned | FastAPI routes, streaming progress |
| Phase 7 — CLI | ⏳ Planned | Click CLI, rich tables, direct mode |
| Phase 8 — Frontend | ⏳ Planned | React + Cytoscape.js graph UI |
| Phase 9 — Docker + Docs | ⏳ Planned | docker-compose, hardening |

---

## Architecture

```
xint/
├── scraper/        # Playwright browser automation, proxy/UA rotation, rate limiting
├── graph/          # networkx / Neo4j backends, relationship logic, similarity scoring
├── api/            # FastAPI, serves data to CLI and frontend
├── frontend/       # React + Cytoscape.js graph visualization
├── cli/            # Click CLI wrapping the API (or direct mode)
└── storage/        # SQLite (dev) / Postgres (prod) via SQLAlchemy async ORM
```

Full design: [ARCHITECTURE.md](ARCHITECTURE.md) | Implementation plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

---

## Quickstart

**Requirements:** Python 3.10, Node.js 18+

```bash
# Clone
git clone https://github.com/gahlautabhinav/xint.git
cd xint

# Python environment
py -3.10 -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
python -m playwright install chromium

# Configure
cp .env.example .env
# Edit .env — all settings have sensible defaults, no changes needed for local dev

# Verify
pytest
```

Once more phases are complete:

```bash
# Start API server
uvicorn api.main:app --reload

# CLI — crawl a user (API mode)
osint crawl start <username> --depth 2

# CLI — inspect without server (direct mode)
osint account get <username> --direct

# Frontend
cd frontend && npm install && npm run dev
```

---

## Proxy Setup (optional)

The tool works without proxies but will use your real IP. For production use, supply a proxy list:

```bash
cp config/proxies.txt.example config/proxies.txt
# Edit config/proxies.txt — one proxy per line:
# http://host:port
# http://user:pass@host:port
# socks5://host:port
```

Free proxies (low reliability, dev only): `osint config proxy refresh`

---

## Configuration

All settings via `.env` (copy from `.env.example`). Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/osint.db` | Switch to `postgresql+asyncpg://...` for prod |
| `GRAPH_BACKEND` | `networkx` | `networkx` (default) or `neo4j` |
| `RATE_PROFILE` | `moderate` | `conservative` / `moderate` / `aggressive` |
| `DEFAULT_DEPTH` | `2` | Crawl depth (1–4) |
| `BROWSER_POOL_SIZE` | `3` | Concurrent browser contexts |

---

## Contributing

See [ARCHITECTURE.md](ARCHITECTURE.md) for module boundaries and design decisions. Each phase maps to a feature branch — see the build status table above.

---

## License

MIT — see [LICENSE](LICENSE).
