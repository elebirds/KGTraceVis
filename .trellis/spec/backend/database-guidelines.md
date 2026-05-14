# Database Guidelines

KGTraceVis is moving to database-backed runtime infrastructure. Neo4j is the
runtime KG backend, Postgres is the runtime application-state backend, and
CSV/JSON files are retained as reproducible seed/import/export artifacts.

## Current Backends

| Backend | Purpose | Example |
|---|---|---|
| Neo4j | runtime KG storage and graph traversal | `Neo4jKGRepository` |
| Postgres | runtime app state, run history, feedback, drafts | `src/kgtracevis/service/postgres_schema.sql` |
| CSV files | tracked KG seed/import/export artifacts | `data/kg/nodes.csv`, `data/kg/edges.csv` |
| JSON/JSONL | evidence fixtures and reproducible paper artifacts | `data/examples/`, `runs/`, `outputs/` |

## CSV Node Contract

Node CSV files must include:

```csv
id,name,label,scenario,aliases,description
```

Rules:

- `id` uses PascalCase, e.g. `ScratchDefect`.
- `scenario` is one of `mvtec`, `tep`, `wafer`, or `shared`.
- `aliases` uses `|`, `;`, or `,` separated aliases.
- Do not create dataset-specific node schemas.

## CSV Edge Contract

Edge CSV files must include:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

Rules:

- `relation` uses uppercase snake case, e.g. `HAS_MORPHOLOGY`.
- `confidence` is a float in `[0, 1]`.
- `weight` is normally `1 - confidence`.
- `review_status` is `auto`, `reviewed`, or `rejected`.
- Feedback counters are non-negative integers.
- Every edge must preserve source and evidence text.
- Do not overwrite reviewed triples automatically.

## Runtime Loading Pattern

Use `Neo4jKGRepository` for runtime KG queries. Every dataset-specific runtime
query must include the selected dataset plus `shared`.

```text
mvtec evidence -> shared + mvtec
wafer evidence -> shared + wafer
tep evidence   -> shared + tep
```

Use `KnowledgeGraph.from_default_paths()` only for seed/import validation,
focused unit tests, and backward-compatible scripts that have not yet been
migrated to the runtime repository.

Use `KnowledgeGraph.from_csv()` only when a test intentionally wants a single
node/edge CSV pair without reference layers.

Legacy/import example:

```python
graph = KnowledgeGraph.from_default_paths()
summary = dry_run_import(graph)
```

## Merge Rules

`KnowledgeGraph.from_paths()` supports multi-file loading:

- Deduplicate identical nodes and edges.
- Raise on conflicting node definitions.
- Raise if a reviewed edge would be overwritten unless
  `allow_reviewed_overwrite=True`.
- Allow missing default reference files only when `skip_missing=True`.

## KG Construction Helper Rules

Use helpers under `src/kgtracevis/kg_construction/` for source-constrained KG
construction:

- Candidate entities and triples must include `source_id` or `source`.
- Candidate triples must include evidence text or a source row reference.
- Assign confidence from source type, then set `weight` to `1 - confidence`
  unless an explicit reviewed value is provided.
- Run `validate_kg_csv_contract()` before exporting KG CSV rows.
- `scripts/build_kg.py` validates and summarizes the merged development KG by
  default; exact duplicate rows may already be collapsed by
  `KnowledgeGraph.from_paths()`, so use focused tests when source-row duplicate
  detection itself matters.

### Convention: Candidate Status Is Structured Metadata

Mechanism node IDs and display names should describe the concept, not its review
state. Use `CableInsulationDamage`, `ParticleContamination`, or
`EdgeProcessIssue` rather than appending `Candidate` to the node ID/name.

Candidate or plausible status belongs in edge-level fields and evidence:

- `review_status=auto`
- conservative `confidence` and matching `weight`
- source IDs such as `mvtec_object_specific_visual_rule`
- evidence text that states the relation is a low-confidence candidate or
  investigation target

This keeps paper/demo graph labels readable while preserving claim boundaries.
Do not remove candidate/plausible wording from edge evidence when the source
does not support a verified RCA claim.

### Convention: Private Source Provenance Must Stay Pattern-Scoped

Private factory summaries, SOPs, logs, and recipe files may support
low-confidence candidate edges, but their provenance must not leak through
shared mechanism nodes. Attach a private source ID only to the exact
pattern/mechanism relation supported by the private summary.

For example, if a wet-clean SOP mentions `nearfull` residue or rinse issues,
`NearfullDefect -> RinseFlowInsufficient` can use the private SOP source with
`review_status=auto` and low confidence. A shared semantic edge such as
`LocalClusterSignature -> ProcessNonuniformity` should keep a generic project
rule source unless the private source explicitly mentions `Loc`.

Tests for private-source KG extensions should assert both the positive edge and
the absence of leakage onto nearby/shared classes.

## Scenario: Neo4j + Postgres Runtime Foundation

### 1. Scope / Trigger

Use this when adding database runtime code, Docker deployment wiring, runtime KG
queries, app-state persistence, or schema migrations.

### 2. Signatures

- Neo4j import: `uv run python scripts/import_kg.py [--config ...] [--dry-run]`
- Postgres init: `uv run python scripts/init_postgres.py [--dsn ...] [--dry-run]`
- Runtime KG repository: `Neo4jKGRepository.candidates(...)`,
  `has_edge(...)`, `outgoing(...)`, and `edge_between(...)`
- Postgres schema source: `src/kgtracevis/service/postgres_schema.sql`

### 3. Contracts

- Neo4j environment keys: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`,
  `NEO4J_DATABASE`
- KG runtime selection: analysis defaults to a dataset-scoped Neo4j snapshot.
  CSV graph loading is allowed only for seed/import validation and focused tests.
- Postgres environment keys: `KGTRACE_POSTGRES_DSN`, or
  `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`
- Neo4j KG truth: node IDs, edge IDs, scenario, relation type, source, evidence,
  confidence, review status, feedback counters
- Postgres app truth: evidence cases, analysis runs, linked entities,
  consistency checks, correction candidates, ranked paths, feedback, drafts,
  review actions, artifacts, KG version metadata
- API run history and feedback default to Postgres. Uploaded files may remain
  artifact files, but `/api/runs` list/detail and `/api/feedback` must not use
  legacy `runs/rootlens_sessions` or `runs/web_sessions` JSON as runtime
  fallback.
- `analysis_runs.run_id` is the public API run ID. New service run IDs must be
  UUID strings rather than mapped through an `external_run_id`.
- Do not add a run-detail snapshot table; reconstruct API details from
  normalized runtime tables.

### 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| Missing Postgres DSN for real init | raise `PostgresInitError` with config guidance |
| Missing Postgres schema file | raise `ValueError` naming the path |
| Missing Neo4j config for real import | raise `Neo4jImportError` with config guidance |
| Invalid dynamic relation type | raise `ValueError` |
| Runtime KG query has dataset | restrict to `[shared, dataset]` |
| Runtime KG query has no dataset | allow all known scenarios only for browse/admin views |

### 5. Good/Base/Bad Cases

- Good: `dataset=mvtec` query returns only `shared` and `mvtec` KG entities.
- Base: `scripts/import_kg.py --dry-run` validates tracked CSV seed rows without
  connecting to Neo4j.
- Bad: a wafer analysis path traverses MVTec-specific plausible mechanism edges.

### 6. Tests Required

- Config resolution precedence for Neo4j and Postgres.
- Postgres schema contains core runtime tables and can be dry-run loaded.
- Neo4j importer creates constraints/indexes before importing nodes and edges.
- Neo4j runtime repository passes `[shared, dataset]` scenario scopes.
- Dynamic Neo4j relation strings reject non-contract relation names.

### 7. Wrong vs Correct

#### Wrong

```python
records = session.run("MATCH (n:KGEntity) RETURN n", {})
```

#### Correct

```python
records = session.run(
    "MATCH (n:KGEntity) WHERE n.scenario IN $scenarios RETURN n",
    {"scenarios": ["shared", dataset]},
)
```

#### Wrong

```python
# Postgres stores a second full copy of all KG edges.
```

#### Correct

```python
# Postgres stores run/path/feedback rows with stable Neo4j node_id, edge_id,
# scenario, and kg_version references.
```

## Common Mistakes

- Treating MVTec plausible RCA edges as verified factory root causes.
- Adding KG edges without `source`, `evidence`, `confidence`, or
  `review_status`.
- Putting generated experiment output into tracked KG CSV files.
- Requiring Neo4j for tests that should run against the in-memory graph.
