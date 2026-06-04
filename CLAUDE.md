# TwitterOSINT — Project Context

## What We're Building

Open-source Twitter/X OSINT network mapping tool. Given a seed username, builds a relationship graph of connected accounts via posts, mentions, followings, and cross-platform profile links.

## Architecture: Modular Monolith

Single repo, strict module boundaries. Easy contributor onboarding. Split into microservices only when load justifies it.

```
osint-twitter/
├── scraper/        # Playwright browser automation, proxy/UA rotation, rate limiting
├── graph/          # Neo4j or networkx, relationship logic, similarity scoring
├── api/            # FastAPI, serves data to CLI and frontend
├── frontend/       # React + D3/Cytoscape.js graph visualization
├── cli/            # Click CLI wrapping the API
└── storage/        # SQLite (dev) / Postgres (prod) abstraction layer
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Scraper | Python + Playwright (browser automation) |
| Graph DB | Neo4j (or networkx for lightweight) |
| Relational DB | SQLite → Postgres |
| API | FastAPI |
| Frontend | React + Cytoscape.js or D3.js |
| CLI | Python Click |
| Proxy rotation | Pluggable — reads `proxies.txt`, user supplies list |

## Data Collection Scope

Given a seed username, collect:
- **Followers network** — who the target follows
- **Mention network** — accounts mentioned in their tweets
- **Interaction network** — accounts they reply to / quote tweet
- **Cross-platform links** — bio links, pinned tweet links, website field → detect Instagram, GitHub, LinkedIn, TikTok handles
- **Cross-platform pivot** — attempt data pull from detected linked platforms

## Anti-Detection Strategy

- Playwright (full browser, not requests) — renders JS, passes most bot checks
- User-Agent rotation — large pool of real browser UA strings
- Human-like delays — random 2-8s between requests, variable scroll patterns
- Pluggable proxy support — `proxies.txt` list, rotates per session
- Cookie/session management — persist sessions to avoid repeated logins

## Output Formats

1. **CLI** — JSON/CSV dumps, filterable queries
2. **Interactive graph UI** — React web app, click to expand nodes, filter by relationship type
3. **Local database** — SQLite/Postgres, run custom SQL queries, export

## Key Design Decisions

- **No official X API** — scraping only (Playwright), no API key required to use
- **Pluggable proxies** — tool reads proxy list, user sources their own IPs
- **Free proxy strategy for dev** — proxyscrape.com daily scrape + alive filter
- **Open source first** — MIT license, clean module boundaries for contributors

## Python Version

Always use `py -3.10` for all Python invocations on this machine.

## Status

Design phase — brainstorming complete, writing implementation plan next.
