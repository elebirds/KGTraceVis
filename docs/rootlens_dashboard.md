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

On first load, the dashboard shows the API bootstrap state, supported upload
modes, accepted file extensions, and exact local example paths. If no runs have
been created, the history and detail panes stay in empty states until a user
uploads a file or selects an existing run.

## Example Uploads

Use records mode for the most repeatable demo path:

```text
data/examples/records/mvtec_records.jsonl
data/examples/records/wm811k_records.jsonl
```

Use evidence mode for a single unified evidence JSON:

```text
data/examples/mvtec_noisy_morphology_demo.json
data/examples/tep_example.json
data/examples/wafer_example.json
```

Image mode is intentionally local-asset dependent. It expects one MVTec-style
image and a locally available model preset/checkpoint; it is not required for
the baseline dashboard smoke.

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

The dashboard displays the stable `target_key` for the selected review target
and submits it in feedback metadata. This is only a review affordance; RootLens
v1 does not implement a full KG editor, KG mutation workflow, or LLM
source-to-KG construction UI.

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

Dashboard contract smoke:

```bash
uv run python scripts/smoke_rootlens_dashboard.py
```

The smoke uses FastAPI `TestClient` instead of launching a browser. It exercises
the same API path used by the Vite client: bootstrap, producer-record upload,
run history, run detail, and review feedback. By default it stores run and
feedback artifacts in a temporary directory; pass this if you want to inspect
the generated manifest afterward:

```bash
uv run python scripts/smoke_rootlens_dashboard.py --persist-runs runs/rootlens_smoke
```

Optional browser spot check:

```bash
uv run python scripts/run_web_api.py
cd web
npm run dev
```

Then open `http://127.0.0.1:5173`, upload
`data/examples/records/mvtec_records.jsonl` in producer-record mode, select the
new history row, and submit `Needs review` for one target.
