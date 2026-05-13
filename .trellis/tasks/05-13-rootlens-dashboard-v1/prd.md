# RootLens Dashboard v1

## Goal

Build the first clean RootLens dashboard after removing the legacy Streamlit and
old React/Vite demos. The dashboard should make the system's basic workflow real:

```text
upload sample -> producer/adapter/KG reasoning -> saved run history
-> inspect evidence/path/provenance -> review feedback
```

This task should produce a foundation-first dashboard platform skeleton and a
minimal end-to-end UI workflow, not a polished paper-demo UI and not the full
future KG construction studio.

## What I Already Know

- The old `web/` and Streamlit surfaces were removed in the cleanup task.
- The maintained backend foundation is `src/kgtracevis/service/` with
  `scripts/run_web_api.py`.
- The FastAPI service already exposes:
  - `GET /api/health`
  - `GET /api/runs`
  - `GET /api/runs/{run_id}`
  - `POST /api/runs/upload`
  - `GET /api/runs/mvtec-model-presets`
  - `POST /api/model-assets/download`
  - `POST /api/analyze`
  - `POST /api/what-if`
  - `POST /api/feedback`
- `src/kgtracevis/service/runs.py` already persists uploaded run manifests under
  `runs/web_sessions` and supports evidence/records/image upload modes.
- MVTec image upload requires object/model context; WM811K can be handled first
  through records upload or later through a dedicated wafer-map upload path.
- The paper needs a dashboard that supports upload-first analysis, run history,
  source/provenance inspection, and human-review-compatible graph management.

## Assumptions

- Frontend will be recreated under a new `web/` directory as a clean React +
  TypeScript + Vite app.
- FastAPI remains the backend API for the dashboard.
- The first UI can call existing backend endpoints; backend changes should be
  minimal and only fill missing API contracts required for the workflow.
- Review feedback can initially write JSON feedback records through the existing
  feedback API; full KG promotion/editing is out of scope for v1.
- The user chose a foundation-first strategy: stable contracts, state model, run
  storage, feedback/review schema, and frontend project structure should take
  priority over visual polish.

## Requirements

### Foundation-First Platform Contracts

- Define a stable dashboard data contract for frontend consumption:
  - `RunSummary`;
  - `RunDetail`;
  - `WorkflowStep`;
  - evidence summary;
  - linked entity summary;
  - correction candidate summary;
  - path summary;
  - source edge provenance;
  - feedback/review request and response.
- Add a dashboard bootstrap endpoint if useful, for example
  `GET /api/dashboard/bootstrap`, returning health/status, supported upload modes,
  model presets, claim-boundary wording, and recent runs.
- Keep schema and response shapes compatible with future KG management and source
  construction modules.

### Run Store And Artifact Contract

- Stabilize run history naming and artifact contracts for the dashboard.
- Prefer `runs/rootlens_sessions` for new dashboard runs while preserving
  compatibility with existing `runs/web_sessions` if needed.
- Ensure manifests expose enough paths and metadata for later case replay,
  feedback review, and paper artifact export.

### Upload-First Analyze Workspace

- Users can select a scenario/mode:
  - MVTec image upload;
  - producer record upload for MVTec/WM811K/TEP-compatible records;
  - evidence JSON upload.
- Users can configure core form fields:
  - `top_k`;
  - dataset override where relevant;
  - MVTec object name and model preset for image upload.
- Submitting an upload calls `POST /api/runs/upload`.
- Success should create a run and immediately show the run detail.

### Run History

- The dashboard lists persisted runs from `GET /api/runs`.
- Selecting a run loads `GET /api/runs/{run_id}`.
- The run list should be scan-friendly: created time, source filename, mode,
  dataset, case count, model backend/preset, status.

### Evidence And Reasoning Detail

- The detail view should show:
  - workflow steps;
  - raw/normalized evidence summary;
  - linked entities;
  - consistency score and inconsistent fields;
  - correction candidates;
  - top-k candidate/plausible paths;
  - source edge provenance for each path.
- Claim boundaries must be visible wherever candidate RCA paths are displayed.

### Human Review Compatibility

- The first dashboard should include review affordances for a selected path or
  edge:
  - accept;
  - reject;
  - needs review / note.
- Review actions should call the existing feedback endpoint or a small backend
  extension if the existing endpoint is insufficient.
- Review state should be treated as feedback/history, not direct mutation of the
  base KG.
- The feedback contract should support at least:
  - `target_type`: `path`, `edge`, `entity_link`, or `correction`;
  - `target_id`;
  - `action`: `accept`, `reject`, or `needs_review`;
  - optional note/reviewer/source metadata.

### Frontend Foundation

- Recreate `web/` as a clean React + TypeScript + Vite project.
- Include an API client layer and shared TypeScript types matching the backend
  dashboard contract.
- Include a simple state model for:
  - bootstrap data;
  - upload form state;
  - run list;
  - selected run detail;
  - selected path/edge review state.
- Include routing/layout shell only as needed for the first workflow.
- Frontend should build/typecheck successfully.

### UX Direction

- This is an operational analysis dashboard, not a landing page.
- First screen should be the analysis workspace with upload + history + detail
  layout.
- Visual style should be dense, calm, and scan-oriented.
- Avoid decorative marketing sections.
- In this task, UI polish is secondary to stable contracts and maintainable
  frontend/backend boundaries.

## Acceptance Criteria

- A clean `web/` app exists and can be run locally.
- The app can connect to the FastAPI backend health endpoint.
- A dashboard bootstrap/contract path exists or the equivalent API client
  initialization is explicitly documented.
- A user can upload at least one existing example records/evidence file through
  the UI and see the resulting run detail.
- Run history can list and reload previous runs.
- Top-k paths and edge provenance are visible for a run.
- A review action can be submitted and persisted/acknowledged.
- README or docs include the new local development commands for API + dashboard.
- Tests cover backend dashboard contract and feedback/review behavior.
- Frontend build/typecheck passes.

## Out Of Scope

- Full force-directed KG editing studio.
- LLM source-to-KG generation workflow.
- Promoting reviewed edges into tracked `data/kg/`.
- Full TEP producer integration, unless the existing Evidence/records contract is
  enough to display TEP-compatible uploaded records.
- Advanced authentication, deployment, or multi-user state.

## Decisions

- Dashboard v1 prioritizes engineering foundation over paper-demo visual polish.
  UI should be usable and professional, but the main deliverable is a stable
  upload/history/reasoning/review platform boundary for later KG construction and
  force-graph management work.

## Technical Notes

- Existing backend files inspected:
  - `src/kgtracevis/service/api.py`
  - `src/kgtracevis/service/runs.py`
  - `tests/test_service_api.py`
- The backend already has the core upload/history endpoints needed for v1.
- Future implementation should keep frontend logic separate from core pipeline
  logic; reusable analysis should remain under `src/kgtracevis/`.
