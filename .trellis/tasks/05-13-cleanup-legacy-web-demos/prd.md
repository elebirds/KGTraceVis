# Clean Up Legacy Web Demos For RootLens Dashboard

## Background

KGTraceVis currently contains two older user-facing web/demo surfaces:

- a Streamlit demo under `src/kgtracevis/app/` with `scripts/run_app.py`;
- an older React/Vite frontend under `web/`.

The paper direction has shifted toward a fuller RootLens dashboard with upload-first
analysis, run history, traceable reasoning, source-grounded KG construction, and
human-review graph management. The existing Streamlit app and old React frontend
are no longer the desired product surface and create architectural/documentation
noise.

The FastAPI service under `src/kgtracevis/service/` should remain because it is
the intended backend foundation for the future dashboard.

## Goal

Remove legacy UI surfaces so the repository has a clean boundary for a future
RootLens dashboard rebuild:

```text
src/kgtracevis/core/              # reasoning core
src/kgtracevis/service/           # FastAPI backend API, retained
src/kgtracevis/kg_construction/   # KG generation/review
scripts/                          # experiments + service CLI
# web/ will be recreated later as the new RootLens dashboard
```

## Scope

### Remove

- Entire legacy `web/` directory, including old Vite/React sources, build output,
  package files, and local node_modules if present.
- Streamlit demo code under `src/kgtracevis/app/` if it is only used by the
  deprecated demo.
- `scripts/run_app.py`.
- Streamlit-specific tests such as `tests/test_streamlit_app.py`.
- README/docs references that present Streamlit or the old `web/` as the current
  UI entry point.

### Keep

- `src/kgtracevis/service/`.
- `scripts/run_web_api.py`.
- service tests and API contracts that will support the new dashboard.
- core KGTracePipeline, adapters, producer, KG construction, and evidence logic.

### Update

- README and docs should state that the legacy Streamlit/React demos were removed
  and that the maintained web-facing backend is the FastAPI service.
- If dependency entries are now unused only because of Streamlit, remove or move
  them conservatively.
- Tests should be adjusted so removing the old UI does not reduce coverage for
  core/service behavior.

## Acceptance Criteria

- `web/` no longer exists in the tracked worktree.
- No import/runtime references to `kgtracevis.app.streamlit_app` remain.
- No user-facing docs instruct users to run the deleted Streamlit demo or old web
  frontend.
- FastAPI service imports and tests continue to pass.
- Quality gates pass:
  - `uv run --extra dev pytest`
  - `uv run --extra dev ruff check .`
  - `uv run --extra dev mypy src tests scripts`
  - `uv run python scripts/run_examples.py`

## Non-Goals

- Do not implement the new RootLens dashboard in this task.
- Do not change service API behavior unless needed to remove stale UI coupling.
- Do not delete generated experiment artifacts under `runs/`.
- Do not remove FastAPI/uvicorn dependencies used by `src/kgtracevis/service/`.
