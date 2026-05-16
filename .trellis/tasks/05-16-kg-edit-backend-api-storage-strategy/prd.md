# brainstorm: KG edit backend API and storage strategy

## Goal

Implement backend-only KG modification APIs for KGTraceVis so operators can add,
update, review, and retire KG nodes/edges without hand-editing tracked CSV files.
The design must also clarify the authority boundary between CSV seed files,
Neo4j runtime graph storage, and Postgres audit/metadata storage.

## What I already know

* The user wants KG modification functionality and only needs backend APIs for
  now; frontend changes are out of scope unless needed for API compatibility.
* Current default seed KG is stored in `data/kg/*.csv` and loaded via
  `DEFAULT_NODE_PATHS` / `DEFAULT_EDGE_PATHS` in `src/kgtracevis/kg/graph.py`.
* TEP Root-KGD assets are stored separately under `data/kg/tep_root_kgd/` as
  JSONL/JSON assets.
* Current source KG compiler build API writes generated candidate outputs under
  `runs/source_kg_builds/<output_name>/nodes.csv` and `edges.csv`.
* KG Studio currently scans older candidate directories including
  `runs/source_kg_build`, `runs/paper_case_kg`, and
  `runs/end_to_end_interpretability_audit/candidate_kg`.
* Runtime `KGTracePipeline` defaults to Neo4j snapshots unless an explicit
  in-memory `KnowledgeGraph` is injected.
* `POST /api/kg/drafts` records advisory draft feedback in
  `runs/kg_drafts.jsonl` and explicitly does not mutate KG artifacts.
* `POST /api/kg/construction/builds/{run_id}/review` exists, but current
  implementation rejects mutation for source KG compiler builds.
* Postgres schema already contains `kg_versions`, `kg_edit_drafts`, and
  `kg_review_actions` tables, but there is no implemented service/API that
  turns those into authoritative node/edge changes.

## Assumptions (temporary)

* CSV files should remain reproducible seed/export artifacts, not the primary
  write target for interactive API edits.
* Neo4j should be the online runtime graph for analysis queries.
* Postgres should record edit intents, review/audit history, version metadata,
  and publication state.
* For v0, KG edits should stay source-constrained and should not silently invent
  unsupported facts.

## Open Questions

* None for the current MVP.

## Requirements (evolving)

* Add backend APIs for manual KG node/edge changes.
* Allow users to add, update, and delete KG nodes in the Neo4j runtime graph.
* Allow users to add and delete KG edges in the Neo4j runtime graph.
* Allow users to update KG edge confidence; edge weight should stay consistent
  with `1 - confidence`.
* Preserve required KG edge provenance fields: `source`, `evidence`,
  `confidence`, `review_status`, and feedback counters.
* Keep backend behavior compatible with existing CSV schemas and Neo4j import
  semantics.
* Avoid frontend work in this task.
* Do not add special handling to prevent later seed CSV import from overwriting
  matching Neo4j rows.

## Acceptance Criteria (evolving)

* [x] API can create or update a KG node through a typed request model.
* [x] API can create or update a KG edge through a typed request model.
* [x] API can delete a KG node from Neo4j.
* [x] API can delete a KG edge from Neo4j.
* [x] API can update only an edge confidence and derived weight.
* [ ] API writes an auditable edit/review record.
* [x] Tests cover successful edits and validation failures.
* [x] Storage strategy is documented in the task notes or project docs.

## Definition of Done

* Tests added/updated for service and API behavior.
* `uv run --extra dev pytest` or a focused pytest subset is run.
* Documentation/notes updated if behavior changes.
* Rollback/export strategy considered.

## Out of Scope (explicit)

* Frontend KG editing UI.
* Full role-based permission system.
* Bulk CSV editor UI.
* Automatic publication of source KG compiler outputs as verified facts.
* Rewriting TEP Root-KGD JSONL asset generation.

## Technical Notes

* `src/kgtracevis/kg/graph.py` defines CSV schema constants and default KG layer
  paths.
* `src/kgtracevis/kg/import_neo4j.py` supports importing validated CSV-backed
  `KnowledgeGraph` rows into Neo4j.
* `src/kgtracevis/kg/neo4j_repository.py` is read-oriented today.
* `src/kgtracevis/service/api.py` has KG draft, material, construction, and
  feedback routes but no node/edge CRUD route.
* `src/kgtracevis/service/postgres_schema.sql` already defines tables that can
  support audit/draft concepts.
* Current docs in `docs/kg_construction.md` describe an older review endpoint
  that mutates `edges.csv`; current code does not do that.
* Runtime API analysis paths mostly read Neo4j through `KGTracePipeline`:
  `KGTracePipeline.graph_for_evidence()` connects to
  `Neo4jKGRepository.connect(resolve_neo4j_config())` when no explicit graph is
  injected.
* `create_run_from_upload()` builds the runtime pipeline via
  `workflows.root_cause_provider_selection.build_pipeline()`, which injects the
  TEP Root-KGD reasoner and otherwise still uses Neo4j when no graph is passed.
* `handlers._analysis_envelope()` currently creates plain `KGTracePipeline()`
  for `/api/analyze` and case-detail style paths; this still reads Neo4j for the
  graph snapshot, but does not inject the TEP Root-KGD provider.
* CSV is still used by scripts/tests and explicit overlay runs:
  `scripts/run_examples.py --kg-node-path/--kg-edge-path`,
  `experiments.adapter_pipeline.run_adapter_pipeline(kg_node_paths=...)`, and
  TEP evaluation when `use_neo4j_runtime=False`.
* Docker Compose starts `kg-import` before the API; `kg-import` runs
  `scripts/import_kg.py` to import seed CSV rows into Neo4j. The API service then
  reads Neo4j using `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and
  `NEO4J_DATABASE`.
* Compose mounts named volumes `neo4j_data:/data` and
  `postgres_data:/var/lib/postgresql/data`, so writes persist across container
  restarts while the named volumes exist. They do not update checked-in CSV
  files.
* TEP Root-KGD is a special hybrid: `TepRootKgdRcaProvider` loads static model
  assets from `data/kg/tep_root_kgd/` and receives the current runtime
  `KnowledgeGraph` snapshot for overlay/source-edge metadata.
* `KGTracePipeline` caches one graph snapshot per dataset in `_graph_cache`.
  Current API paths usually instantiate a fresh pipeline per request, but any
  future process-wide singleton would need cache invalidation after KG edits.

## Storage Strategy Notes

### Recommended v0 Direction

Use **Neo4j as the online KG runtime store**, **Postgres as the audit/version
control plane**, and **CSV as reproducible seed/export artifacts**.

This matches the current runtime direction: analysis already expects Neo4j when
no explicit graph is injected, while CSV import/export is still valuable for
paper reproducibility, fixtures, and rollback. Directly treating CSV as the
interactive write database would make concurrency, validation, review history,
and rollback brittle.

### User Decision

Use Approach B for v0, but do **not** add import-time protection for reviewed or
manual rows. Manual edits write to Neo4j and may be overwritten by a later
explicit CSV seed import if the imported node/edge IDs match.

### Feasible Approaches

**Approach A: CSV-first editor**

* How it works: API rewrites `data/kg/*.csv` or build-layer CSVs directly.
* Pros: simple, transparent, easy to diff in Git.
* Cons: poor concurrency, hard audit story, risky around reviewed triples, not
  aligned with Neo4j runtime.

**Approach B: Neo4j runtime writes + Postgres audit** (recommended MVP)

* How it works: API validates requests, records an audit row in Postgres if
  configured, and writes node/edge changes to Neo4j. CSV export can be added as
  an explicit later step.
* Pros: aligns with runtime graph, keeps edits immediately queryable, avoids
  mutating seed CSVs.
* Cons: requires Neo4j availability for edits; Postgres fallback needs careful
  handling if not configured.

**Approach C: Postgres draft/publish workflow**

* How it works: API writes edits as draft rows in Postgres; a publish endpoint
  materializes reviewed changes to Neo4j and/or CSV.
* Pros: strongest review/versioning boundary.
* Cons: larger scope; edits are not immediately visible in runtime analysis.

## Expansion Sweep

* Future evolution: versioned KG releases, CSV export snapshots, rollback, and
  source KG compiler review-to-publish workflows.
* Related scenarios: manual curation should align with feedback capture,
  construction review, and Neo4j import behavior.
* Failure/edge cases: duplicate nodes, missing edge endpoints, invalid
  relations, rejected/reviewed triple overwrite rules, Neo4j or Postgres being
  unavailable, and audit/write partial failure.
