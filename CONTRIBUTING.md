# Contributing to xint

Thanks for your interest. xint is MIT-licensed and welcomes contributions.

---

## Setup

**Requirements:** Python 3.10, Node.js 18+

```bash
git clone https://github.com/gahlautabhinav/xint.git
cd xint

py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate         # macOS/Linux

py -3.10 -m pip install -e ".[dev]"
py -3.10 -m playwright install chromium
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # dev server on :5173, proxies /api → :8000
```

---

## Running tests

```bash
py -3.10 -m pytest                  # full suite (~397 tests, offline)
py -3.10 -m pytest -m live          # live browser tests (needs auth + network)
py -3.10 -m ruff check .            # linter
py -3.10 -m mypy .                  # type checker
```

All three gates must be green before submitting a PR.

---

## Python conventions

- **Always `py -3.10`** — never bare `python`, `python3`, or `pip`. The repo is pinned to 3.10.
- Async SQLAlchemy throughout — no sync sessions anywhere.
- Repository pattern only — no raw SQL in route handlers or business logic (except explicit backfill queries).
- New endpoints: add Pydantic schema in `api/schemas/`, route in the appropriate router, tests in `tests/test_api.py`.

---

## Frontend conventions

- TypeScript throughout. No `any` without a comment explaining why.
- Styles in a co-located `.css` file (e.g. `features/bias/bias.css`), using CSS variables from the design system (`--c-*`, `--s-*`, `--r-*`).
- TanStack Query for all server state. No direct `fetch` calls — use `api.*` from `src/lib/api.ts`.
- `refetchInterval` minimum 3000ms on polling queries (prevents Windows socket exhaustion under heavy crawls).

---

## Selectors

Twitter/X DOM changes frequently. Selectors live in `scraper/extractors/twitter.py` under `SELECTOR_REGISTRY["v1"]`. When X breaks something:

1. Open a GitHub issue with the broken selector and the new one.
2. Update `SELECTOR_REGISTRY` and bump the version key.
3. Update `tests/fixtures/snapshots/` if the snapshot is stale.
4. Run `py -3.10 scripts/validate_selectors.py` manually against live X before merging.

---

## Branch and PR workflow

1. Branch from `main`: `git checkout -b feat/short-description`
2. Keep PRs focused — one feature or fix per PR.
3. Commit messages: imperative mood, present tense (`add geo map page`, not `added geo map page`).
4. All CI checks green (`pytest` + `ruff` + `mypy` + `npm run build`).
5. For frontend changes: smoke-test the golden path in a browser before submitting.

---

## What not to contribute

- New external API dependencies without discussion in an issue first.
- Hardcoded credentials, API keys, or email addresses — these must go in `.env` (gitignored).
- Scraping techniques designed to be used against accounts without authorization — see [DISCLAIMER.md](DISCLAIMER.md).

---

## Security issues

Report vulnerabilities privately via [SECURITY.md](SECURITY.md). Do not open a public issue.
