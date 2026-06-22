# xint — Twitter/X OSINT Network Mapper

> Open-source intelligence tool for mapping Twitter/X relationship networks. Given a seed username, builds a full graph of connected accounts via follows, followers, mentions, replies, and cross-platform profile links.

> **Read [DISCLAIMER.md](DISCLAIMER.md) before use.** Scraping Twitter/X may violate their Terms of Service. You are solely responsible for legal compliance in your jurisdiction.

---

## Features

- **Network crawl** — follows, followers, mentions, replies, quote tweets, retweets up to configurable depth
- **Cross-platform detection** — detects Instagram, GitHub, LinkedIn, TikTok, YouTube, Telegram, Discord handles from bios and pinned tweets
- **Contact + enrichment** — publicly-posted emails/phones, location, join date, profile image, tweet geo-tags (t.co links expanded first)
- **Posting-timezone inference** — buckets tweet timestamps to estimate an account's likely UTC offset (heuristic OSINT signal)
- **Hashtag co-occurrence** — ranks hashtags and surfaces account pairs sharing them (`GET /graph/hashtags`)
- **Username enumeration** — Sherlock-style check across ~28 platforms; surfaces where a handle exists (`GET /enrich/username`)
- **Identity resolution** — cross-references GitHub, GitLab, Keybase public APIs to find linked accounts (`GET /enrich/identity`)
- **OSINT pivots** — reverse-image search links, breach-check hints, dossier aggregation (`GET /enrich/pivots`)
- **Geo map** — geocodes account location fields via Nominatim, plots on an interactive Leaflet map (`GET /geo/locations`)
- **Network intersection** — Jaccard similarity + common-nodes graph for two or more seed accounts (`GET /graph/intersection`)
- **Bias agent integration** — optional [xint-bias-agent](https://github.com/gahlautabhinav/xint-bias-agent) sidecar; crawls auto-send timelines for classification; on-demand analysis via UI
- **Dossier page** — single-account deep-dive: profile, relationships, cross-platform links, bias flags
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
py -3.10 -m pip install -e ".[dev]"
py -3.10 -m playwright install chromium

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
| Graph Explorer | `/` | Interactive network graph — search seed, drag nodes, zoom, focus |
| Jobs | `/jobs` | List all crawls, start a new one, delete finished jobs |
| Job Detail | `/jobs/<id>` | Live terminal log, progress bar, Stop button for running jobs |
| Accounts | `/accounts` | Searchable table of all scraped accounts |
| Hashtags | `/hashtags` | Ranked hashtag co-occurrence table |
| Network Intersection | `/intersection` | Jaccard similarity graph for two or more seeds |
| Geo Map | `/geo` | Leaflet map of account location fields |
| Bias Analysis | `/bias` | Bias-agent flag table + on-demand analyze form |
| Dossier | `/dossier/<platform>/<handle>` | Deep-dive profile: bio, relationships, cross-platform links, bias flags, posts & replies tweet feed |

#### Graph Explorer tips

- **Search** a username to load their subgraph
- **Click** a node to open the inspector (bio, follower count, edges)
- **Drag** any node — neighbours repel and settle live (cola physics)
- **Zoom out** — minor nodes' labels fade; hub/root/selected labels stay visible
- **Focus mode** (target icon) — dims everything beyond the selected node's N-hop neighbourhood (1–3 hops, configurable)
- **Filter** edges by type (FOLLOWS, MENTIONS, REPLIES_TO, CROSS_PLATFORM_LINK) via the toolbar

---

## Bias Agent (optional)

xint integrates with [xint-bias-agent](https://github.com/gahlautabhinav/xint-bias-agent), a separate sidecar that classifies Twitter timelines for bias signals using Gemini.

### Setup

1. Clone and configure xint-bias-agent:
   ```bash
   git clone https://github.com/gahlautabhinav/xint-bias-agent
   cd xint-bias-agent
   echo "GEMINI_API_KEY=your_key_here" > .env
   py -3.10 -m src.server   # starts on port 5000
   ```

2. Add to xint's `.env`:
   ```
   BIAS_AGENT_URL=http://127.0.0.1:5000
   ```

3. Restart xint backend. Every crawl will now auto-send timelines to the agent.

### On-demand analysis

From the **Bias** page, enter a `@username` and click **Analyze Now** — xint scrapes the account on-demand and triggers immediate classification.

### Backfill existing data

Push all stored relationships to the bias agent in one shot:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/sync-bias-connections
```

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
| `BIAS_AGENT_URL` | _(none)_ | URL of xint-bias-agent sidecar (e.g. `http://127.0.0.1:5000`); enables bias classification |

> **Upgrading from an older version?** If you had data in `data/osint.db`, rename it to `data/xint.db` (or set `DATABASE_URL=sqlite+aiosqlite:///./data/osint.db` in `.env`).

---

## Running Tests

```bash
py -3.10 -m pytest                          # all tests (410 currently)
py -3.10 -m pytest tests/test_api.py        # API layer only
py -3.10 -m pytest tests/test_crawler.py    # crawler + jobs
py -3.10 -m pytest -m live                  # live browser tests (needs auth + network)
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
