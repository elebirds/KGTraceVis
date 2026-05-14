# KG Construction Publish Dry-Run API

## Goal

Close the backend-only KG construction loop by exposing a safe API action that
loads one completed source-to-KG build, merges it with the default seed KG by
default, and returns Neo4j import counts without writing unless the caller
explicitly confirms publication.

## Context

The current backend can:

- upload single construction source files;
- run source-to-KG builds into candidate `nodes.csv` and `edges.csv`;
- list build manifests;
- inspect build details;
- run read-only CSV QA.

The next missing backend step is publication orchestration. It should reuse the
existing `kg.import_neo4j` importer, but remain a service/use-case action rather
than placing logic in scripts or front-end code.

## Requirements

- Add a service DTO and handler for publishing a construction build.
- Add `POST /api/kg/construction/builds/{run_id}/publish`.
- Default to `dry_run=true` and `include_defaults=true`.
- Return import counts, the selected build, artifact paths, and the claim
  boundary.
- Load the candidate build as an overlay on top of default KG CSV paths unless
  the request sets `include_defaults=false`.
- Reject real Neo4j writes unless `dry_run=false` and `confirm_publish=true`
  are both present.
- Resolve Neo4j settings through the existing config helper for confirmed
  writes.
- Map unknown build IDs to HTTP 404 and unsafe/failed publish requests to HTTP
  400.
- Keep implementation under `src/kgtracevis/`; do not import from `scripts/`.

## Acceptance Criteria

- [x] A caller can build a manual source KG, call publish with `{}`, and receive a
  dry-run response.
- [x] The default dry-run response includes the default seed KG plus candidate
  layer.
- [x] Calling with `{"dry_run": false}` fails before opening a Neo4j connection.
- [x] Existing build registry and validation tests still pass.
- [x] Documentation names the publish endpoint and its safety gate.

## Verification

- `uv run --extra dev ruff check src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py tests/test_service_api.py`
- `uv run --extra dev mypy src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py`
- `uv run --extra dev pytest tests/test_service_api.py -q`
- `uv run --extra dev pytest -q`
- `uv run python scripts/import_kg.py --dry-run`
- `uv run python scripts/run_examples.py`

## Out Of Scope

- Frontend publish controls.
- Human review UI.
- KG version pinning beyond the existing build manifest and artifact paths.
- Automatic confidence updates based on publication.
- Live Neo4j integration tests.
