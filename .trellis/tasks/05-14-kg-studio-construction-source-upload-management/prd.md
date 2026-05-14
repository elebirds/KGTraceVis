# brainstorm: backend KG construction source upload management

## Goal

Implement the backend foundation for KG construction source management before
building more frontend UI. Users should be able to upload a local source file,
have the backend store it under a controlled runtime directory, and receive a
validated source reference that can be passed to the existing
`/api/kg/construction/build` workflow.

## What I already know

- `/api/kg/construction/build` already accepts `KGConstructionSourceInput`
  objects.
- Construction build supports `structured_records`, `manual_table`,
  `tep_semantic_lift`, and `tep_variable_mapping`.
- Inline `source_text` exists, but real source management needs uploaded files
  and stored paths.
- FastAPI routes should be thin and call service/workflow helpers.
- v0 should remain source-constrained and candidate-only; upload does not imply
  KG publication.

## Assumptions

- v0 backend source upload supports single-file source artifacts:
  `manual_table`, `structured_records`, and `tep_variable_mapping`.
- TEP semantic-lift directory/pair management can come later because it needs a
  multi-file bundle or pair registration flow.
- Uploaded files are stored under `runs/source_kg_sources/` and referenced by
  local path in later construction builds.
- The API should return both stored metadata and a ready-to-use
  `KGConstructionSourceInput` payload.

## Requirements

- Add backend DTOs for uploaded construction sources and list responses.
- Add service helper to save uploaded source bytes safely.
- Validate:
  - safe `source_id`;
  - supported `source_type`;
  - supported `source_format`;
  - filename has matching allowed extension;
  - upload is non-empty and below a conservative byte limit.
- Write one metadata JSON sidecar per uploaded source.
- Add API routes:
  - `POST /api/kg/construction/sources/upload`
  - `GET /api/kg/construction/sources`
- Add tests covering successful upload/list and invalid upload rejection.

## Acceptance Criteria

- [x] Uploading a CSV manual table source returns a stored path and
  build-ready source input.
- [x] Listing uploaded construction sources returns uploaded metadata.
- [x] Invalid extension/type/empty upload returns 4xx.
- [x] Existing construction build route still passes.
- [x] Focused service tests pass.

## Definition of Done

- Backend tests added.
- No frontend implementation in this task.
- Docs updated to mention backend source upload API.
- Full or focused quality gate run and recorded.

## Out of Scope

- Frontend source management UI.
- Multi-file TEP semantic-lift bundle upload.
- Live LLM extraction.
- Neo4j publication.
- Durable database-backed source registry.

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
