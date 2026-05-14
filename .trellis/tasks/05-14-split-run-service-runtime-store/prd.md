# refactor: split run service and runtime store

## Goal

Split the oversized `src/kgtracevis/service/runs.py` module into smaller
service/workflow-facing modules and clarify the Postgres runtime store boundary,
without changing public FastAPI contracts or run output shapes.

## What I Already Know

* `service/runs.py` currently mixes run models, upload dispatch, workflow-step
  assembly, evidence/records/image execution, dashboard enrichment, path graph
  construction, review target assembly, visual evidence, model asset helpers,
  and run-store wiring.
* `service/postgres_run_store.py` is the normalized runtime store for API run
  history and feedback.
* The previous backend workflow refactor added `src/kgtracevis/workflows/` for
  reusable non-HTTP orchestration.
* The current request is specifically to address two remaining areas:
  `service/runs.py` size/shape and Postgres runtime store service-layer
  organization.

## Requirements

* Preserve `/api/runs`, `/api/runs/upload`, `/api/runs/{id}`,
  `/api/runs/{id}/artifacts/{name}`, and feedback behavior.
* Move clearly separable service model/enrichment/store-boundary code out of
  `service/runs.py`.
* Keep runtime app-state truth in the Postgres run store contract.
* Do not introduce legacy filesystem runtime fallback.
* Do not change Evidence JSON, KG CSV, or ranked path contracts.
* Do not touch unrelated source-to-KG construction task files.

## Acceptance Criteria

* [x] `service/runs.py` is smaller and delegates at least run models,
      enrichment helpers, and run-store access to focused modules.
* [x] Postgres run store imports depend on stable service models instead of the
      monolithic `service.runs` module.
* [x] Existing service API tests pass.
* [x] Full backend quality gate passes.

## Out Of Scope

* Implementing a new database schema.
* Changing API response fields.
* Replacing `KGTracePipeline`.
* Rewriting every upload workflow in one pass.
* Changing unrelated source-to-KG construction methodology files.

## Technical Notes

Relevant specs:

* `.trellis/spec/backend/workflow-architecture.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/directory-structure.md`
* `.trellis/spec/backend/quality-guidelines.md`
