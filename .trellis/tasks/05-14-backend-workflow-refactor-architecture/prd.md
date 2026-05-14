# brainstorm: backend workflow refactor architecture

## Goal

Refactor KGTraceVis backend orchestration so scripts, FastAPI handlers, and
experiments share reusable workflow modules instead of duplicating analysis,
producer, artifact, and run-session logic. The architecture must also reserve a
clear integration boundary for the in-progress reusable KG pipeline work without
implementing that KG pipeline in this task.

## What I Already Know

* The project already has a clean core analysis facade in
  `src/kgtracevis/core/pipeline.py`.
* FastAPI routes live in `src/kgtracevis/service/api.py` and call handler/helper
  modules.
* `src/kgtracevis/service/runs.py` currently mixes upload handling, run
  persistence, model producer orchestration, visual artifacts, workflow steps,
  and review target assembly.
* Several scripts are more than CLI shells. In particular,
  `scripts/build_dataset_records.py`, `scripts/run_real_model_pipeline.py`, and
  `scripts/run_noise_experiment.py` contain reusable orchestration logic.
* Existing backend specs require reusable logic to live under
  `src/kgtracevis/`; scripts, apps, and services should be clients.
* Runtime architecture is moving toward Neo4j for KG state and Postgres for
  app/run/feedback state, while CSV/JSON remain reproducible artifacts.

## Assumptions

* We should avoid a full MVC rewrite; KGTraceVis is an analysis workflow system,
  not a mostly CRUD web app.
* The right target is a light application/use-case layer, probably
  `src/kgtracevis/workflows/`.
* The reusable KG pipeline under separate development should be represented as a
  provider/contract boundary in architecture docs and specs only in this task.
* First implementation step should be low-risk and testable: move reusable
  script workflows into `src/kgtracevis/workflows/` while preserving CLI behavior.

## Open Questions

* None blocking for the first slice. Naming can be refined later if the team
  prefers `application/` over `workflows/`.

## Requirements

* Document the target backend layering and dependency direction.
* Include the reusable KG pipeline as an architecture dependency and extension
  point without implementing it here.
* Add Trellis backend spec guidance so future work follows the workflow/use-case
  split.
* Move concrete script-owned reusable logic into `src/kgtracevis/workflows/`.
* Keep CLI behavior backward-compatible.
* Do not alter KG CSV, Evidence JSON, or path-ranking output contracts in this
  first slice.

## Acceptance Criteria

* [x] A backend refactor architecture document exists under `docs/`.
* [x] Backend Trellis spec index points to a workflow/use-case architecture
      guideline.
* [x] At least one script becomes a thin CLI over reusable code in
      `src/kgtracevis/workflows/`.
* [x] Additional obvious script orchestration candidates are thinned where
      feasible without changing public contracts.
* [x] Relevant focused tests pass.
* [x] No KG pipeline implementation is added for the external/in-progress KG
      pipeline work.

## Definition Of Done

* Tests added/updated where behavior changes.
* Lint/type-check issues avoided for touched files.
* Docs/specs updated before or alongside implementation.
* Rollback remains simple because the first refactor slice preserves public CLI
  arguments and output shape.

## Out Of Scope

* Implementing the separate reusable KG construction/runtime pipeline.
* Replacing `KGTracePipeline`.
* Migrating all run history to Postgres in this task.
* Rewriting the frontend or changing API response contracts.
* Large-scale migration of every script in one pass.
* Deep `src/kgtracevis/service/runs.py` decomposition beyond clearly separable
  workflow extraction.

## Technical Notes

* Read backend specs:
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/logging-guidelines.md`
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/adapter-guidelines.md`
* Inspected architecture and runtime docs:
  * `docs/project_design.md`
  * `docs/database_runtime.md`
* Candidate refactor slices:
  * move dataset-record build orchestration from `scripts/build_dataset_records.py`
    into `src/kgtracevis/workflows/dataset_records.py`;
  * keep the script as argparse plus a call to the reusable workflow.
  * move noise experiment orchestration from `scripts/run_noise_experiment.py`
    into `src/kgtracevis/workflows/noise_experiment.py`.
  * move real-model demo orchestration from `scripts/run_real_model_pipeline.py`
    into `src/kgtracevis/workflows/real_model_pipeline.py`.
