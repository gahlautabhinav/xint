# Contributing to xint

Thanks for your interest. xint is MIT-licensed and welcomes contributions.

---

## Getting Started

```bash
git clone https://github.com/gahlautabhinav/xint.git
cd xint
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate         # macOS/Linux
pip install -e ".[dev]"
python -m playwright install chromium
pytest                               # should be all green before you start
```

---

## Module boundaries

| Module | Owns | Must NOT |
|--------|------|---------|
| `scraper/` | Browser automation, anti-detect, proxy rotation | Import from `api/` or `cli/` |
| `graph/` | Graph backends, traversal, similarity scoring | Import from `scraper/` |
| `storage/` | SQLAlchemy models, repos, Alembic migrations | Import from `graph/` or `scraper/` |
| `api/` | FastAPI routers, schemas, lifespan | Import from `cli/` |
| `cli/` | Click commands, Rich formatting | Import from `api/` (calls modules directly) |
| `frontend/` | React + Vite, calls REST API only | Import Python modules |

Breaking these boundaries requires discussion first — open an issue.

---

## Conventions

### Python

- **Version:** Python 3.10 only. Use `py -3.10` on Windows; `python3.10` elsewhere.
- **Formatter / linter:** `ruff` (configured in `pyproject.toml`). Run `ruff check .` before committing.
- **Types:** `mypy` with `ignore_missing_imports = true`. Run `mypy <changed files>` before committing.
- **Tests:** `pytest` with `asyncio_mode = "auto"`. Every new feature needs tests. No mocking the database — integration tests hit real SQLite (in-memory for tests).
- **Comments:** Only when the *why* is non-obvious. No docstrings on trivial methods.

### Frontend

- TypeScript strict mode. No `any` unless unavoidable.
- Cytoscape operations go through `GraphCanvas.tsx` — never reach into `cy` from parent components.
- CSS: scoped per-feature (`.feature/feature.css`), no global overrides.
- Run `npm run build` before submitting — build errors block CI.

### Git

- Branch from `main`. Name: `feature/short-description` or `fix/short-description`.
- Commit messages: imperative mood, 72-char subject line, reference an issue if one exists.
- One logical change per commit. Squash WIP commits before opening a PR.

---

## Submitting a PR

1. Fork → branch → change → test → push
2. Open PR against `main`
3. Fill the PR template (summary + test plan)
4. All CI checks must pass: `pytest`, `ruff check .`, `mypy`, `npm run build`
5. A maintainer will review — expect feedback within a few days

### PR checklist

- [ ] `pytest` passes (275+ tests, none skipped without reason)
- [ ] `ruff check .` clean
- [ ] `mypy` clean on changed files
- [ ] `npm run build` clean (if frontend changed)
- [ ] No new secrets or credentials committed
- [ ] `config/sessions/` and `data/*.db` are gitignored — don't commit them

---

## Reporting bugs

Use [GitHub Issues](https://github.com/gahlautabhinav/xint/issues). Include:

- OS and Python version
- Full error output / traceback
- Steps to reproduce (minimal)
- What you expected vs what happened

For security issues — see [SECURITY.md](SECURITY.md) instead.

---

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be respectful.
