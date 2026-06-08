# Security Policy

## Supported Versions

Only the latest commit on `main` is actively maintained.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Open a [private security advisory](https://github.com/gahlautabhinav/xint/security/advisories/new) on GitHub.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

You will receive acknowledgment within 48 hours. Fixes are typically released
within 7 days for high-severity issues.

## Scope

This tool is a local scraping utility. Key attack surfaces:

| Area | Notes |
|------|-------|
| Session cookies | Stored in `config/sessions/` — gitignored, never committed |
| API key | Optional; passed via `X-API-Key` header. Set `API_KEY` in `.env`. |
| Proxy credentials | `config/proxies.txt` — gitignored, never committed |
| Database | Local SQLite by default. Postgres requires standard credential hygiene. |

## Out of Scope

- Issues with third-party sites being scraped (X/Twitter, etc.)
- Proxy provider security
- Legal issues around scraping (see [DISCLAIMER.md](DISCLAIMER.md))
