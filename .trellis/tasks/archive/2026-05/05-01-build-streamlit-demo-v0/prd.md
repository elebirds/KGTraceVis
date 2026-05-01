# Build Streamlit Demo V0

## Goal

Replace the Streamlit placeholder with a lightweight local demo that exposes the
current KGTraceVis v0 reasoning loop over checked-in example evidence.

## Requirements

- Load example evidence JSON files from `data/examples`.
- Let the user select a case.
- Show raw evidence and normalized/KG analysis outputs.
- Run `KGTracePipeline` instead of duplicating analysis logic.
- Show:
  - linked entities,
  - consistency score,
  - inconsistent fields,
  - correction candidates,
  - top-k RCA paths,
  - source edge provenance for paths/corrections.
- Include a simple what-if editor for core fields:
  - anomaly type,
  - location,
  - morphology,
  - variables,
  - log events.
- Keep UI lightweight and local; no auth, service, or database dependency.

## Acceptance Criteria

- [x] Streamlit app calls `KGTracePipeline`.
- [x] App can analyze all checked-in example cases.
- [x] App exposes linked entities, consistency, corrections, and paths.
- [x] What-if edits produce valid `Evidence` and re-run analysis.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.
- [x] `uv run python scripts/run_app.py` prints the runnable command.
- [x] Streamlit server smoke test returns non-empty HTML on localhost.

## Out Of Scope

- No custom frontend.
- No persistent feedback store.
- No Neo4j dependency.
- No external datasets.
- No generated screenshots committed.

## Technical Notes

- Main file: `src/kgtracevis/app/streamlit_app.py`
- Helper entry: `scripts/run_app.py`
- Optional tests may cover pure helper functions if app code exposes them.
