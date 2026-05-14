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

## Runtime Run Service Boundary

Postgres-backed run history should depend on stable service DTOs and payload
helpers, not on the monolithic upload orchestration module.

Current split:

```text
service/run_models.py             # RunSummary, RunDetail, WorkflowStep
service/run_store.py              # runtime store provider and test override
service/run_enrichment.py         # path graph, review targets, dashboard fields
service/postgres_run_payloads.py  # row-to-payload and payload-to-row helpers
service/postgres_run_store.py     # Postgres SQL coordination
service/runs.py                   # upload dispatch and public compatibility facade
```

`PostgresRunStore` must not import from `kgtracevis.service.runs`; that would
couple runtime persistence to upload orchestration and makes future service
splits brittle. If the store needs API payload shapes, import from
`run_models.py`, `run_enrichment.py`, or `postgres_run_payloads.py`.

Backward-compatible re-exports from `service.runs` are allowed for public API
tests and existing service callers, but new code should import the focused
module directly.

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

## Scenario: Candidate KG Overlay Validation

### 1. Scope / Trigger

Use this when a source-to-KG construction run produces candidate `nodes.csv` and
`edges.csv` artifacts that should be tested with the reasoning pipeline or
prepared for Neo4j publication.

### 2. Signatures

- Build candidate CSVs: `uv run python scripts/build_source_kg.py ...`
- Run examples with candidate overlay:
  `uv run python scripts/run_examples.py --kg-node-path <nodes.csv> --kg-edge-path <edges.csv>`
- Validate import overlay:
  `uv run python scripts/import_kg.py --include-defaults --nodes <nodes.csv> --edges <edges.csv> --dry-run`
- Construction manifest:
  `kg_construction_manifest.json` with `artifact_type=source_to_kg_construction_manifest_v1`

### 3. Contracts

- Candidate CSVs must obey the existing KG node and edge contracts.
- Source-to-KG builds write `nodes.csv`, `edges.csv`,
  `kg_construction_summary.json`, and `kg_construction_manifest.json`.
- The construction manifest must include run metadata, source payloads,
  flattened draft rows, summary counts, artifact paths, and append-only review
  decisions when available.
- Candidate layers are appended after `DEFAULT_NODE_PATHS` and
  `DEFAULT_EDGE_PATHS` when `--include-defaults` or example overlay flags are
  used.
- `run_examples.py` reports `kg_backend=explicit_seed_overlay` when explicit KG
  CSV paths are supplied.
- TEP semantic-lift `full_kg_entity_ids` are entity-resolution cluster members,
  not KGTraceVis node aliases. Do not import them into `aliases` unless the
  alias-review and endpoint-rewrite logic explicitly supports that behavior.

### 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| Candidate edge head/tail missing from constructed nodes | construction runner raises `ValueError` before CSV export |
| Candidate overlay conflicts with a reviewed default edge | graph merge raises unless overwrite is explicitly allowed |
| Custom import paths without `--include-defaults` | import only those custom paths |
| Custom import paths with `--include-defaults` | append custom paths to default KG layers |
| KG Studio sees `nodes.csv` / `edges.csv` with a manifest | expose manifest path and payload in the Studio bootstrap response |
| KG Studio review action is submitted | persist an append-only review decision; do not mutate KG CSV files |
| TEP cluster member imported as alias and collapses an `ALIGNS_TO` node | treat as a construction bug; keep cluster members in metadata/evidence instead |

### 5. Good/Base/Bad Cases

- Good: build a TEP candidate layer, run examples with the overlay, then dry-run
  import with `--include-defaults`.
- Base: `scripts/import_kg.py --dry-run` validates the tracked seed KG only.
- Bad: publish candidate CSVs to Neo4j before confirming all edge endpoints
  exist in the merged graph.

### 6. Tests Required

- Construction tests assert candidate edge endpoints exist after node cleaning.
- TEP importer tests assert `full_kg_entity_ids` do not collapse explicit
  `ALIGNS_TO` alias nodes.
- CLI tests assert `import_kg.py --include-defaults` increases row counts over
  overlay-only import.
- CLI tests assert `run_examples.py --kg-node-path ... --kg-edge-path ...`
  reports `explicit_seed_overlay`.
- Manifest tests assert source-to-KG builds write
  `kg_construction_manifest.json` with draft rows and artifact paths.
- KG Studio tests assert both legacy candidate CSV names and source-to-KG build
  artifact names are readable.

### 7. Wrong vs Correct

Wrong:

```text
semantic_lift.full_kg_entity_ids -> KGNode.aliases
```

Correct:

```text
semantic_lift.node_id/entity_id/tep_channel -> KGNode.aliases
semantic_lift.full_kg_entity_ids -> draft metadata or evidence only
```

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
