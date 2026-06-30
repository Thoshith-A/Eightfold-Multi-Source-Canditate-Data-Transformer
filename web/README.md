# Web layer (optional, Stage 9)

A **thin** FastAPI app that wraps the *same* `transformer.pipeline` — it contains
no extraction/merge/projection logic of its own — plus a minimal React/Vite
frontend that renders the canonical profile with **confidence bars**,
**source chips**, and a **provenance table** (and an "LLM" badge on any field the
optional enrichment lane filled).

> Pure presentation over the same JSON. The deterministic core does not depend on
> any of this; the API is gated behind the `[web]` extra.

## Run it

```bash
# 1. Backend (serves the built frontend at / when dist/ exists)
pip install -e ".[web]"
python -m uvicorn transformer.web.api:app --reload --port 8000
#   open http://localhost:8000

# 2. Frontend dev server (hot reload; proxies /api -> :8000)
cd web/frontend
npm install
npm run dev          # open http://localhost:5173
#   …or build static assets the backend serves directly:
npm run build        # -> web/frontend/dist/  (FastAPI mounts this at /)
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | liveness |
| GET | `/api/configs` | named sample configs (for the UI dropdown) |
| POST | `/api/transform` | upload sources (`files`) + `config` + `enrich` → projected JSON |
| POST | `/api/transform/samples` | run on the bundled `samples/sources` (one-click demo) |

Response shape: `{ candidates: [...], count, enriched, enrichment_report: [...] }`.
Uploaded filenames are reduced to their basename (no path traversal); uploads are
written to an isolated temp dir and deleted after the run.

## Notes
- The optional **3D presentation skin was deliberately not built** — the brief
  marks it as never-required and "cut it the moment the core needs work." A
  verified, accessible 2D UI is the right call for an ATS.
- `npm audit` reports advisories in the Vite/esbuild **dev** toolchain (not
  shipped to users). Not addressed here to keep the lockfile reproducible; a
  production deploy would pin/patch them.
