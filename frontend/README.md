# xint — frontend

Interactive OSINT network-graph explorer for the xint API. React + Vite +
TypeScript, Cytoscape.js for graph rendering, TanStack Query for data.

Design language: an xAI-inspired dark canvas — near-black surface, white pill
outlines, geometric sans display (Geist) paired with uppercase tracked mono
labels (Geist Mono). See `../scripts/DESIGN-x.ai.md`.

## Routes

| Path                        | View                                                                          |
| --------------------------- | ----------------------------------------------------------------------------- |
| `/`                         | **Graph Explorer** — search a seed handle, render relationship graph, drag-   |
|                             | reactive cola physics, zoom-aware labels, local focus mode.                   |
| `/jobs`                     | **Jobs** — start a crawl, list all jobs, delete finished ones.                |
| `/jobs/:id`                 | Job detail — live terminal-style event log, progress bar, Stop/Delete buttons.|
| `/accounts`                 | **Accounts** — searchable table of every scraped profile.                     |
| `/hashtags`                 | **Hashtags** — ranked hashtag co-occurrence table.                            |
| `/intersection`             | **Network Intersection** — Jaccard similarity graph for two or more seeds.    |
| `/geo`                      | **Geo Map** — Leaflet map of account location fields (Nominatim geocoding).   |
| `/bias`                     | **Bias Analysis** — bias-agent flag table + on-demand Analyze Now form.       |
| `/dossier/:platform/:handle`| **Dossier** — deep-dive profile: bio, relationships, cross-platform, bias.    |

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
merges incremental results into a live Cytoscape instance via `cy.add()`.
Node detail comes from `GET /accounts/{platform}/{handle}`. Username enumeration
is triggered via `GET /enrich/username`. Jobs use `POST /jobs`, `GET /jobs`,
`GET /jobs/{id}`, and the poll-based `GET /jobs/{id}/events`. Bias classification
calls `POST /jobs/analyze-now` and reads `GET /enrich/bias`.
