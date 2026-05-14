# brainstorm: backend KG construction build registry

## Goal

Add backend APIs that make source-to-KG construction builds discoverable,
inspectable, and independently validatable before any publish-to-Neo4j work is
attempted.

## What I already know

- Source uploads are now backend-supported and return build-ready source inputs.
- `/api/kg/construction/build` writes `nodes.csv`, `edges.csv`,
  `kg_construction_summary.json`, and `kg_construction_manifest.json`.
- KG Studio has internal artifact discovery logic, but the backend does not yet
  expose a registry of all construction builds.
- `kgtracevis.kg_construction.qa.run_kg_qa` already provides structured CSV QA.

## Assumptions

- The registry is file-backed in v0 and scans `runs/source_kg_build/*`.
- Only directories with `kg_construction_manifest.json` are registry entries.
- Validation runs QA on the candidate build's `nodes.csv` and `edges.csv`.
- Publish/import-to-Neo4j remains out of scope.

## Requirements

- Add DTOs for build summary, build detail, build list, and build validation.
- Add service helpers to:
  - list build manifests;
  - retrieve one build by `run_id`;
  - validate one build with KG QA.
- Add API routes:
  - `GET /api/kg/construction/builds`
  - `GET /api/kg/construction/builds/{run_id}`
  - `POST /api/kg/construction/builds/{run_id}/validate`
- Keep errors explicit for unknown builds or missing artifacts.
- Add service API tests for list/detail/validation and unknown build behavior.

## Acceptance Criteria

- [x] Build list returns a created construction run under a patched test root.
- [x] Build detail returns manifest, summary, and artifact paths.
- [x] Build validation returns a structured QA report and pass/fail summary.
- [x] Unknown run ID returns 404.
- [x] Existing build/upload routes still pass.

## Definition of Done

- Backend tests added.
- Docs updated with registry endpoints.
- No frontend or Neo4j publish implementation.
- Focused and broad checks recorded.

## Out of Scope

- Publish-to-Neo4j API.
- Selected runtime KG version.
- Frontend build registry UI.
- Database-backed registry.

## Technical Notes

- Relevant files:
  - `src/kgtracevis/service/kg_construction.py`
  - `src/kgtracevis/service/api.py`
  - `tests/test_service_api.py`
  - `docs/kg_construction.md`

## Verification Notes

- `uv run --extra dev pytest tests/test_service_api.py -q` passed.
- `uv run --extra dev pytest tests/test_source_kg_construction_workflow.py tests/test_kg_construction_pipeline.py tests/test_kg_studio.py -q` passed.
- `uv run --extra dev ruff check src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py tests/test_service_api.py` passed.
- `uv run --extra dev mypy src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py tests/test_service_api.py` passed.
- `uv run --extra dev pytest` passed.
- `uv run --extra dev ruff check .` passed.
- `uv run --extra dev mypy src tests scripts` passed.
- `uv run python scripts/run_examples.py` passed.
