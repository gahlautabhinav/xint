# TwitterOSINT

Open-source Twitter/X OSINT network mapping tool. Given a seed username, builds a relationship graph of connected accounts via posts, mentions, followings, and cross-platform profile links.

> **Read [DISCLAIMER.md](DISCLAIMER.md) before use.** Scraping Twitter/X may violate their ToS. You are responsible for legal compliance.

## Features

- Follower/following network mapping
- Mention and interaction network extraction
- Cross-platform handle detection (Instagram, GitHub, LinkedIn, TikTok, YouTube, Telegram, Discord, Substack)
- Interactive graph visualization (React + Cytoscape.js)
- CLI and REST API interfaces
- Pluggable proxy rotation (supply your own `proxies.txt`)
- Anti-detection: playwright-stealth, UA rotation, human-like delays

## Quickstart

**Requirements:** Python 3.10, Node.js 18+

```powershell
# Clone and enter the project
git clone <repo-url>
cd twitter-osint

# Python environment
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
py -3.10 -m pip install -e ".[dev]"
py -3.10 -m playwright install chromium

# Configuration
cp .env.example .env
# Edit .env as needed

# Verify installation
pytest
```

## Usage

```powershell
# Crawl a user (API mode — start API server first)
uvicorn api.main:app --reload
osint crawl start elonmusk --depth 2

# Direct mode (no API server needed)
osint account get elonmusk --direct

# Frontend
cd frontend && npm install && npm run dev
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full design documentation.

## License

MIT — see [LICENSE](LICENSE).
