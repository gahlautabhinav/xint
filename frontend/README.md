# xint — frontend

Interactive OSINT network-graph explorer for the xint API. React + Vite +
TypeScript, Cytoscape.js for graph rendering, TanStack Query for data.

Design language: an xAI-inspired dark canvas — near-black surface, white pill
outlines, geometric sans display (Geist) paired with uppercase tracked mono
labels (Geist Mono). See `../scripts/DESIGN-x.ai.md`.

## Routes

| Path             | View                                                        |
| ---------------- | ----------------------------------------------------------- |
| `/`              | **Graph Explorer** — search a seed handle, render its       |
|                  | relationship graph, click/​double-click nodes to expand,    |
|                  | filter by relationship type, inspect any account.           |
| `/jobs`          | **Jobs** — start a crawl and watch live progress.           |
| `/jobs/:id`      | Job detail with a live-streaming event log.                 |
| `/accounts`      | **Accounts** — searchable table of every scraped profile.   |

## Develop

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api/*` → `http://localhost:8000` (the FastAPI backend),
so run the API alongside it:

```bash
# from the repo root
.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

### Configuration

All optional — see `.env.example`:

- `VITE_API_BASE_URL` — absolute API origin for a deployed build. Unset in dev
  to use the `/api` proxy.
- `VITE_API_KEY` — sent as `X-API-Key`; only needed if the backend set `API_KEY`.

## Build

```bash
npm run build        # type-checks then emits to dist/
npm run preview      # serve the production build locally
```

## Data flow

The explorer reads `GET /graph/{handle}/subgraph` for the initial network and
`GET /graph/{handle}/subgraph?depth=1` per node when expanding, merging results
into a live Cytoscape instance. Node detail is enriched from
`GET /accounts/{platform}/{handle}`. Jobs use `POST /jobs`, `GET /jobs`,
`GET /jobs/{id}` and the poll-based `GET /jobs/{id}/events`.
