# xint — Twitter/X OSINT Network Mapper

> Open-source intelligence tool for mapping Twitter/X relationship networks. Given a seed username, builds a full graph of connected accounts via follows, followers, mentions, replies, and cross-platform profile links.

> **Read [DISCLAIMER.md](DISCLAIMER.md) before use.** Scraping Twitter/X may violate their Terms of Service. You are solely responsible for legal compliance in your jurisdiction.

---

## Features

- **Network crawl** — follows, followers, mentions, replies, quote tweets, **reposts (retweets)** up to configurable depth
- **Cross-platform detection** — detects Instagram, GitHub, LinkedIn, TikTok, YouTube, Telegram, Discord handles from bios and pinned tweets
- **Contact + enrichment** — publicly-posted emails/phones, location, join date, profile image, tweet geo-tags (t.co links expanded first)
- **Posting-timezone inference** — buckets tweet timestamps to estimate an account's likely UTC offset (heuristic OSINT signal)
- **Hashtag co-occurrence** — ranks hashtags and surfaces account pairs sharing them (`xint graph hashtags`, `GET /graph/hashtags`)
- **Live progress** — real-time terminal-style activity log while crawling, per-account events streamed to the UI
- **Interactive graph UI** — React + Cytoscape.js visualization, drag-reactive physics, click-to-expand nodes, local focus mode, zoom-aware labels
- **REST API + CLI** — FastAPI backend, Click CLI (`xint`)
- **Stop + Delete jobs** — cancel a running crawl cleanly, delete finished jobs and their event history
- **Anti-detection** — Playwright (full browser), playwright-stealth, UA rotation, human-like delays, pluggable proxy rotation
- **No official X API required** — scraping only, no API key needed

---

## Architecture

```
xint/
├── scraper/        # Playwright browser automation, proxy/UA rotation, rate limiting
├── graph/          # networkx / Neo4j backends, relationship logic
├── api/            # FastAPI, serves data to CLI and frontend
├── frontend/       # React + Cytoscape.js graph visualization
├── cli/            # Click CLI
└── storage/        # SQLite (dev) / Postgres (prod) via SQLAlchemy async ORM
```

---

## Quick Setup

**Requirements:** Python 3.10, Node.js 18+

```bash
# 1. Clone
git clone https://github.com/gahlautabhinav/xint.git
cd xint

# 2. Python environment
py -3.10 -m venv .venv

# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 3. Install
pip install -e ".[dev]"
python -m playwright install chromium

# 4. Verify
pytest
```

That's it — no `.env` changes needed for local dev. SQLite is used by default.

---

## Authentication (required for real scraping)

xint needs an authenticated X/Twitter session to scrape profiles. **Do this once before your first crawl.**

### Cookie method (recommended)

1. Open [x.com](https://x.com) in a browser where you're logged in
2. Open DevTools → **Application** tab → **Cookies** → `https://x.com`
3. Copy the values of `auth_token` and `ct0`
4. Run:

```bash
xint login --cookies
# Paste auth_token and ct0 when prompted
```

### Check login status

```bash
xint auth status        # shows whether a session is saved + token snippet
xint auth revoke        # delete session (then re-run login to switch accounts)
```

---

## CLI Usage

```bash
# Authenticate first
xint login --cookies

# Crawl a user (depth 2, up to 200 accounts)
xint crawl elonmusk --depth 2 --max-accounts 200

# List all jobs
xint jobs list

# View a specific job
xint jobs show <job-id>

# Search accounts scraped so far
xint accounts list
xint accounts search alice

# Export graph
xint graph export elonmusk -o graph.json
xint graph export elonmusk -o graph.csv --format csv

# Hashtag ranking + accounts sharing hashtags
xint graph hashtags --min-shared 2

# Auth management
xint auth status
xint auth revoke
```

### Full CLI reference

```
xint --help
xint crawl --help
xint jobs --help
xint accounts --help
xint graph --help
xint auth --help
```

---

## Web UI

The web UI gives you a live view of running crawls, a searchable jobs list, and an interactive graph explorer.

### Start the API server

```bash
# Windows — must use Proactor event loop for Playwright compatibility
uvicorn api.main:app --reload
# Runs on http://127.0.0.1:8000
```

### Start the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Using the UI

| Page | URL | What it does |
|------|-----|--------------|
| Jobs | `/jobs` | List all crawls, start a new one, delete finished jobs |
| Job Detail | `/jobs/<id>` | Live terminal log, progress bar, Stop button for running jobs |
| Graph Explorer | `/graph` | Interactive network graph — search seed, drag nodes, zoom, focus |

#### Graph Explorer tips

- **Search** a username to load their subgraph
- **Click** a node to open the inspector (bio, follower count, edges)
- **Drag** any node — neighbours repel and settle live (cola physics)
- **Zoom out** — minor nodes' labels fade; hub/root/selected labels stay visible
- **Focus mode** (target icon) — dims everything beyond the selected node's N-hop neighbourhood (1–3 hops, configurable)
- **Filter** edges by type (FOLLOWS, MENTIONS, REPLIES_TO, CROSS_PLATFORM_LINK) via the toolbar

---

## Proxy Setup (optional)

The tool works without proxies (uses your real IP). For production:

```bash
# Create proxy list
cp config/proxies.txt.example config/proxies.txt
# Edit config/proxies.txt — one proxy per line:
# http://host:port
# http://user:pass@host:port
# socks5://host:port
```

---

## Configuration

All settings via `.env` (or environment variables). Copy `.env.example` to `.env` to override defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/xint.db` | Switch to `postgresql+asyncpg://...` for prod |
| `GRAPH_BACKEND` | `networkx` | `networkx` (default) or `neo4j` |
| `RATE_PROFILE` | `moderate` | `conservative` / `moderate` / `aggressive` |
| `DEFAULT_DEPTH` | `2` | Crawl depth (1–4) |
| `BROWSER_POOL_SIZE` | `3` | Concurrent browser contexts |
| `API_KEY` | _(none)_ | Set to require `X-API-Key` header on all API requests |

> **Upgrading from an older version?** If you had data in `data/osint.db`, rename it to `data/xint.db` (or set `DATABASE_URL=sqlite+aiosqlite:///./data/osint.db` in `.env`).

---

## Running Tests

```bash
pytest                          # all tests (275 currently)
pytest tests/test_api.py        # API layer only
pytest tests/test_crawler.py    # crawler + jobs
pytest -m live                  # live browser tests (needs auth + network)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and PR guide.

---

## Security

Report vulnerabilities via [SECURITY.md](SECURITY.md) — **do not open a public issue**.

---

## License

MIT — see [LICENSE](LICENSE).
