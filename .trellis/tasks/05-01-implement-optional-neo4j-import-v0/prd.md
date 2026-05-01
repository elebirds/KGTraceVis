# Implement Optional Neo4j Import V0

## Goal

Implement optional Neo4j import support for validated KG CSV rows while keeping
the default v0 pipeline, tests, and examples fully runnable without a Neo4j
service.

## Requirements

- Implement reusable import helpers under `src/kgtracevis/kg/import_neo4j.py`.
- Load connection settings from CLI arguments, environment variables, or
  `configs/neo4j.example.yaml`.
- Import validated KG nodes and edges into Neo4j with source/provenance fields.
- Keep CSV/in-memory KG as the reproducible source of truth.
- Update `scripts/import_kg.py` to call reusable helpers and fail clearly when
  a database is requested but unavailable.
- Do not make `pytest`, `run_examples.py`, or normal pipeline usage require a
  running Neo4j instance.
- Use fake driver/session tests for Cypher behavior.

## Acceptance Criteria

- [x] Tests cover config resolution without real Neo4j.
- [x] Tests cover node/edge Cypher execution with a fake session.
- [x] Tests verify edge provenance fields are passed to Neo4j.
- [x] `scripts/import_kg.py --dry-run` or equivalent runs without Neo4j.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.

## Out Of Scope

- No path querying through Neo4j yet.
- No mandatory database in CI/local tests.
- No Docker orchestration.
- No new KG facts.

## Technical Notes

- Expected files:
  - `src/kgtracevis/kg/import_neo4j.py`
  - `scripts/import_kg.py`
  - focused tests under `tests/`
