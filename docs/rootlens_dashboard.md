# RootLens Dashboard v1

RootLens v1 is a foundation-first dashboard boundary for KGTraceVis. It keeps
analysis logic in `src/kgtracevis/`, uses the FastAPI service as the dashboard
contract, and keeps the React client under `web/` focused on upload, run
history, evidence/path inspection, provenance, and review feedback.

## Local Development

Start the API:

```bash
uv run python scripts/run_web_api.py
```

Start the dashboard:

```bash
cd web
npm install
npm run dev
```

The API runs on `http://127.0.0.1:8000`. Vite runs on
`http://127.0.0.1:5173` and proxies `/api` to the API server.

## Contract Endpoints

- `GET /api/dashboard/bootstrap` returns status, supported datasets, upload
  modes, feedback targets/actions, MVTec model presets, claim-boundary wording,
  and recent runs.
- `POST /api/runs/upload` accepts evidence JSON, producer records, or one
  MVTec image upload.
- `GET /api/runs` lists persisted run summaries from `runs/rootlens_sessions/`
  and legacy `runs/web_sessions/`.
- `GET /api/runs/{run_id}` returns a run detail with workflow steps, evidence
  summary, linked entities, correction candidates, top-k paths, source edge
  provenance, and review targets. Each review target includes a stable
  `target_key` in addition to `target_type` and `target_id` so UI state can
  distinguish different target categories with similar IDs.
- `POST /api/feedback` appends review feedback records with `target_type`,
  `target_id`, `action`, optional note/reviewer/source metadata, and run/case
  context.

Review feedback is append-only history under `runs/web_feedback/feedback.jsonl`.
It does not promote or mutate KG CSV edges.

## Checks

Backend:

```bash
uv run --extra dev pytest
uv run python scripts/run_examples.py
```

Frontend:

```bash
cd web
npm run typecheck
npm run build
```
