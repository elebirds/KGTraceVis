# brainstorm: Neo4j and Postgres runtime migration

## Goal

Move KGTraceVis from file-backed runtime state toward deployable database-backed runtime infrastructure: Neo4j is the runtime knowledge graph backend, Postgres is the application state store, and Docker provides a quick local deployment path.

## What I already know

* The user wants to stop treating CSV/JSON as the runtime backend.
* Runtime KG access should move directly to Neo4j.
* Postgres is preferred over SQLite for evidence cases, analysis runs, feedback, drafts, and review state.
* CSV/JSON may remain as seed/import/export artifacts, but not as the runtime backend.
* Docker should be added for quick local deployment.

## Assumptions

* v0 should introduce infrastructure and repository boundaries without requiring every existing analysis flow to be fully rewritten in one pass.
* Neo4j remains the source of truth for KG nodes, KG edges, scenario separation, and path traversal.
* Postgres does not duplicate the full KG; it stores stable references to Neo4j node IDs, edge IDs, scenario, and KG version.
* Existing tests should pass with explicit graph fixtures where needed; runtime scripts should use Neo4j by default.

## Requirements

* Add Docker Compose services for Neo4j and Postgres.
* Add environment/config documentation for database URLs and credentials.
* Add Postgres schema migrations for evidence cases, analysis runs, linking results, consistency checks, correction candidates, ranked paths, feedback records, KG drafts, KG review actions, artifacts, source documents, and KG versions.
* Add Python database connection/config helpers for Postgres.
* Add a Neo4j repository boundary for runtime KG access.
* Keep KG access scenario-aware: dataset-specific queries must include the selected dataset plus `shared`.
* Preserve CSV as import/seed material only, not as the long-term runtime backend.
* Do not keep a CSV runtime fallback in `KGTracePipeline`.

## Acceptance Criteria

* [x] `docker compose up` can start Neo4j and Postgres for local development.
* [x] Postgres schema can be initialized reproducibly from a script.
* [x] Neo4j constraints/import path remain runnable from scripts.
* [x] New code has focused tests for config/schema/repository behavior that do not require accidental global state.
* [x] README or docs explain the database-backed runtime setup.

## Definition of Done

* Tests added/updated where appropriate.
* Existing test suite remains green or any failures are clearly documented.
* Documentation updated for the new database/runtime workflow.
* Rollout boundary is explicit: database runtime foundation first, full pipeline migration in follow-up work if needed.

## Out of Scope

* Removing every CSV/NetworkX helper in this task.
* Implementing authentication, multi-user roles, or cloud deployment.
* Migrating large external datasets into Postgres.
* Treating MVTec plausible mechanisms as verified root-cause labels.

## Technical Notes

* Repo is Trellis-managed; backend and frontend specs should be read before code changes.
* Existing AGENTS guidance requires Neo4j Python driver and source-constrained KG edges.
* This task should avoid introducing dataset-specific evidence schemas.
* Implemented v0 foundation in this task:
  * Docker Compose for Neo4j, Postgres, and the FastAPI backend.
  * Postgres schema and `scripts/init_postgres.py`.
  * Neo4j schema initialization and `Neo4jKGRepository`.
  * `KGTracePipeline` defaults to Neo4j runtime snapshots when no explicit test/import graph is provided.
  * Runtime documentation in README and `docs/database_runtime.md`.
  * Backend database guideline updated so future work treats Neo4j/Postgres as runtime infrastructure.
* Verification completed:
  * `docker compose up -d neo4j postgres`
  * `uv run python scripts/init_postgres.py`
  * `uv run python scripts/import_kg.py`
  * `uv run python scripts/run_examples.py`
  * `docker compose build api`
  * `docker compose up -d api`
  * `curl -sS http://localhost:8000/api/dashboard/bootstrap`
  * `uv run --extra dev pytest`
  * `uv run --extra dev ruff check .`
  * `uv run --extra dev mypy src tests scripts`
