# RootLens Dashboard v1

RootLens v1 is a foundation-first dashboard boundary for KGTraceVis. It keeps
analysis logic in `src/kgtracevis/`, uses the FastAPI service as the dashboard
contract, and keeps the React client under `web/` focused on upload, run
history, evidence/path inspection, path graph provenance, KG candidate review,
and review feedback.

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

On first load, the dashboard opens to an Overview page rather than a single
mixed workspace. Navigation separates the demo into four focused pages:

- Overview: API/KG/run status and next actions.
- Intake: upload modes, accepted file extensions, exact local example paths,
  and run history.
- Case Analysis: selected-run evidence, path graph, provenance, and review
  queue.
- KG Studio: source registry, source-to-KG drafts, candidate graph, edge
  provenance, and KG draft adjustments.

If no runs have been created, Intake and Case Analysis show empty states until
a user uploads a file or selects an existing run.

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
  summary, linked entities, correction candidates, top-k paths, a derived
  `path_graph`, source edge provenance, and review targets. Each review target includes a stable
  `target_key` in addition to `target_type` and `target_id` so UI state can
  distinguish different target categories with similar IDs.
- `GET /api/kg/studio` returns the read-only KG Studio payload: source registry
  rows, local source documents, the selected candidate KG artifact directory,
  node/edge counts, validation summary, bounded graph preview, and edge review
  targets.
- `POST /api/kg/source-draft` converts structured source lines into
  schema-compatible candidate edge drafts. The default `heuristic` provider runs
  without external LLM credentials and keeps all generated rows review-only.
- `POST /api/feedback` appends review feedback records with `target_type`,
  `target_id`, `action`, optional note/reviewer/source metadata, and run/case
  context.

Review feedback is append-only history under `runs/web_feedback/feedback.jsonl`.
It does not promote or mutate KG CSV edges.

The run detail view includes a Path Graph workspace. Candidate reasoning paths
are rendered as compact node-edge chains; selecting a path changes the current
review target, and selecting an edge exposes the KG edge source, confidence,
review status, and evidence text. The Review panel groups available path, edge,
entity-link, and correction targets into a queue and submits the stable
`target_key` in feedback metadata.

This is only a review affordance; RootLens v1 does not implement a full KG
editor, KG mutation workflow, or LLM source-to-KG construction UI.

## KG Studio

The KG Studio panel reads candidate KG artifacts from local generated outputs.
It prefers `runs/paper_case_kg/` and falls back to
`runs/end_to_end_interpretability_audit/candidate_kg/`. If neither directory is
present, the panel stays in an empty state and still shows any available source
registry/source document metadata.

The panel is intentionally non-mutating. It previews candidate KG edges, shows
source/evidence/confidence/review status, and includes a force-directed SVG
graph preview for visual edge selection. It submits edge review feedback via the
same append-only `/api/feedback` route used by case reasoning.

The Draft Adjustment form writes append-only JSONL records through
`POST /api/kg/drafts` into `runs/kg_studio_drafts/drafts.jsonl`. Draft actions
can mark an edge as keep/revise/reject/promote-later and optionally propose a
weaker relation, evidence wording, or confidence. Accepted feedback and draft
records do not update candidate CSVs or tracked `data/kg/` files in this
foundation version.

The Source-to-KG Draft form accepts structured lines in this format:

```text
head,relation,tail,scenario,evidence
```

For example:

```text
ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact,mvtec,Scratch wording supports a candidate contact mechanism.
```

The endpoint returns candidate edges with source, evidence, confidence, weight,
and `review_status=auto`; it does not call a remote LLM or write KG CSV files in
this foundation version. A future LLM provider can reuse the same response
contract.

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
run history, run detail, path graph/review target linkage, and review feedback.
It also exercises the KG Studio route and verifies candidate edge review targets
plus append-only draft submission when local candidate KG artifacts are
available. It always exercises source-to-KG draft generation.
By default it stores run and feedback artifacts in a temporary directory; pass
this if you want to inspect the generated manifest afterward:

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
