# KG Construction Review Queue API

## Goal

Expose a backend-only review queue for source-to-KG construction builds so
clients can list candidate KG edges by status, source, scenario, and relation
before review or publication.

## What I Already Know

- Construction builds already have list/detail/validate/review/publish API
  actions.
- Candidate edge review mutates only the selected build's `edges.csv` and
  appends manifest review decisions.
- Existing service code already has reusable helpers for build discovery,
  artifact validation, and reading edge CSV rows.
- The user wants backend priority before frontend.

## Assumptions

- MVP should expose only edge queue rows because edge trust is the immediate
  publish gate.
- Queue rows should be read-only and should not mutate build files.
- Pagination can be simple offset/limit because build artifact CSVs are small
  for v0.
- Filters should be optional query parameters, not a POST body, because this is
  a read/list action.

## Requirements

- Add `GET /api/kg/construction/builds/{run_id}/review-queue`.
- Return candidate edge rows with stable `target_key` values.
- Support filters for `review_status`, `source`, `scenario`, `relation`, and a
  text query over head/relation/tail/evidence/source.
- Support `offset` and `limit`.
- Return total counts before pagination, returned count, and summary counts for
  review statuses, relations, scenarios, and sources.
- Map unknown build IDs to HTTP 404 and invalid filter/pagination values to
  HTTP 400/422.
- Document the endpoint as the read side of the pre-publish review workflow.

## Acceptance Criteria

- [x] A build's review queue returns candidate edge rows with target keys.
- [x] Filtering by review status reflects accepted/rejected edge changes.
- [x] Filtering by source/scenario/relation/query works deterministically.
- [x] Pagination metadata reports total and returned counts.
- [x] Docs mention the queue endpoint and its intended backend-only role.

## Verification

- `uv run --extra dev ruff check src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py tests/test_service_api.py`
- `uv run --extra dev mypy src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py`
- `uv run --extra dev pytest tests/test_service_api.py -q`
- `uv run --extra dev pytest -q`
- `uv run python scripts/import_kg.py --dry-run`
- `uv run python scripts/run_examples.py`

## Definition Of Done

- Tests added or updated.
- Lint, typecheck, focused service tests, and full tests pass.
- Docs updated.
- Task archived and session journal recorded.

## Out Of Scope

- Frontend review queue UI.
- Node/entity queue.
- Diff against default KG snapshots.
- Batch accept/reject.
- Database-backed review queue persistence.

## Technical Notes

- Expected service files: `src/kgtracevis/service/kg_construction.py`,
  `src/kgtracevis/service/api.py`.
- Expected tests: `tests/test_service_api.py`.
- Follow `.trellis/spec/backend/workflow-architecture.md` and
  `.trellis/spec/backend/error-handling.md`.
