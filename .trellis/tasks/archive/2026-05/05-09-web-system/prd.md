# brainstorm: web system

## Goal

Build a real web entry point for KGTraceVis so a user can load evidence, inspect
the adapter output, run `KGTracePipeline`, and review candidate explanation
paths without using scripts.

## What I already know

* The repo already has a lightweight Streamlit demo at `src/kgtracevis/app/streamlit_app.py`.
* The core pipeline is already working for real MVTec and WM811K inputs.
* The current web need is about a usable system shell, not a new analysis model.
* The project favors reusable backend logic under `src/kgtracevis/` and thin app clients.

## Assumptions (temporary)

* The first web version should use a real web stack rather than Streamlit.
* The page should stay focused on inspection, editing, and candidate-path review.
* Real sample data and example cases are enough for v1; authentication and multi-user workflow are out of scope.

## Open Questions

* Resolved: use React + TypeScript + Vite + TailwindCSS for the first real web
  system.

## Frontend Stack Analysis

Recommended default: React + TypeScript + Vite + TailwindCSS.

Why:

* KGTraceVis will likely need graph/path visualization, dense tables, side
  panels, filters, editable forms, and review actions. React has a broader
  ecosystem for this kind of analytics UI.
* React pairs well with mature building blocks such as TanStack Query, TanStack
  Table, React Flow, shadcn/ui, Radix primitives, and TailwindCSS.
* FastAPI already exposes OpenAPI, so generated or typed API clients can be used
  cleanly from either stack; React has more examples and templates for this
  workflow.
* The repo has no existing Vue or React code, so there is no migration cost.
  In that blank-slate situation, React has the lower long-term ecosystem risk.

Vue remains a reasonable option if the main priority is simpler component
authoring for a small team, but the likely KGTraceVis UI is closer to an
analytics workbench than a simple CRUD app.

## Requirements (evolving)

* Add a FastAPI service layer that exposes example/real evidence cases and
  pipeline analysis results.
* Add a React + TypeScript + Vite frontend under a repo-approved application
  directory.
* Load one evidence case at a time.
* Show raw evidence, normalized evidence, linked entities, consistency score, correction candidates, and top-k paths.
* Allow a small what-if editor to change anomaly fields and rerun analysis.
* Allow basic feedback capture on links, corrections, or paths.
* Support checked-in examples first, then real producer outputs.

## Acceptance Criteria (evolving)

* [ ] A user can open a browser page and inspect an example case end to end.
* [ ] A user can run KG analysis from the page and see candidate explanation paths.
* [ ] A user can edit a few fields and re-run analysis.
* [ ] A user can leave lightweight feedback on a case or path.
* [ ] The UI stays aligned with the existing adapter/pipeline boundary and does not reimplement core logic.

## Definition of Done

* Tests added or updated where appropriate.
* Lint / typecheck / relevant verification green.
* Docs updated if the user-facing behavior changes.
* The app runs locally from the repo with a clear command.

## Out of Scope

* User authentication or multi-tenant accounts.
* A full production backend.
* Training or serving new models.
* Replacing the current core pipeline architecture.

## Technical Notes

* Existing app entry point: `src/kgtracevis/app/streamlit_app.py`
* Existing app dependency group: `app` in `pyproject.toml`
* Existing service placeholders: `src/kgtracevis/service/api.py` and
  `src/kgtracevis/service/handlers.py`
* Core flow already exists: evidence -> adapter -> `KGTracePipeline`
* Real pipeline validation already exists via `scripts/run_real_model_pipeline.py`
* App should call reusable backend code, not duplicate analysis logic

## Proposed Architecture

```text
web frontend (React/TS/Vite/Tailwind)
-> FastAPI service
-> reusable kgtracevis service handlers
-> Evidence adapters / KGTracePipeline
-> JSON response with candidate/plausible explanation paths
```

Backend modules:

* `src/kgtracevis/service/api.py`: FastAPI app factory and route registration.
* `src/kgtracevis/service/handlers.py`: reusable functions for listing cases,
  loading evidence, running analysis, editing what-if fields, and formatting
  API responses.
* Existing `src/kgtracevis/core/`, `adapters/`, and `schema/` remain the source
  of truth.

Frontend modules:

* New React app with TypeScript, Vite, and TailwindCSS.
* Main views: case list, evidence summary, linked entities, consistency and
  corrections, candidate path ranking, raw JSON/provenance drawer.
* Initial graph/path view can be a structured path panel; richer React Flow
  graph interaction can follow after the API contract is stable.

## Implementation Plan

1. Add backend API dependencies and a minimal FastAPI app.
2. Implement service handler functions that wrap existing evidence loading and
   `KGTracePipeline.analyze`.
3. Add route tests for listing cases, getting one case, running analysis, and
   submitting a what-if payload.
4. Scaffold the React + TS + Vite + Tailwind app.
5. Build the first operational screen: case list + analysis detail page.
6. Add candidate path and provenance panels.
7. Add a small what-if editor and feedback capture stub.
8. Add docs and local run commands.

## Initial API Shape

```text
GET  /api/health
GET  /api/cases
GET  /api/cases/{case_id}
POST /api/analyze
POST /api/what-if
POST /api/feedback
```

All analysis responses must keep the existing claim boundary: outputs are
candidate/plausible explanations, not verified root-cause labels.
