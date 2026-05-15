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

Unified RCA results are persisted through stable run payloads as
`ranked_root_causes` and exposed as feedback targets with
`target_type=root_cause_candidate`. When reconstructing Postgres run details,
stored `ranked_root_causes` must be preferred over any fallback projection from
`top_k_paths`.

## Scenario: Unified RCA Runtime Payloads

### 1. Scope / Trigger

- Trigger: changing RCA output, run-detail payloads, dashboard fields,
  feedback targets, or Postgres run persistence.
- Reason: RCA candidates cross the core pipeline, evidence runtime schema,
  service DTOs, Postgres replay, dashboard summaries, and human feedback.

### 2. Signatures

Core pipeline:

```python
class RootCauseProvider(Protocol):
    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        ...
```

Runtime payload fields:

```text
AnalysisResult.ranked_root_causes: list[RankedRootCause]
RunDetail.ranked_root_causes: list[dict]
Evidence.kg_analysis.ranked_root_causes: list[dict]
feedback_records.target_type: root_cause_candidate
```

### 3. Contracts

- `ranked_root_causes` is the canonical RCA ranking output.
- `top_k_paths` remains a compatibility and explanation-path field.
- If a provider returns candidates, preserve those candidates as-is in the
  service/Postgres payload instead of re-deriving from paths.
- If no provider returns candidates, derive a fallback root-cause list from
  `top_k_paths` with `scoring_method=relation_weighted_path`.
- Root-cause candidates must carry stable `ranking_id`, `candidate_id`, `rank`,
  `score`, `scoring_method`, and enough supporting path/evidence data for
  review.
- Review targets for these candidates use
  `target_type=root_cause_candidate` and `target_id=<ranking_id>`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Provider returns RCA candidates | Preserve provider rankings and metadata |
| Provider returns `[]` | Fall back to projection from `top_k_paths` |
| Postgres replay has stored `ranked_root_causes` | Use stored candidates, not path projection |
| Postgres replay lacks stored candidates | Reconstruct fallback candidates from paths |
| Evidence is revalidated with runtime `kg_analysis` | Keep `ranked_root_causes` |
| Feedback target is a root-cause candidate | Store as `root_cause_candidate` |
| Artifact ranking row is unscoped to a TEP scenario | Ignore unless explicitly configured as global |

### 5. Good/Base/Bad Cases

- Good: TEP artifact provider returns `tep_artifact_bridge` candidates with
  selector metadata; Postgres replay returns the same candidates.
- Base: MVTec path ranking produces paths only; pipeline projects them into
  `ranked_root_causes` with path-derived supporting edges.
- Bad: service code rebuilds RCA candidates from paths after a provider already
  produced Root-KGD/RBC-derived candidates.

### 6. Tests Required

- Pipeline serialization asserts both `top_k_paths` and `ranked_root_causes`.
- Evidence schema tests assert `KGAnalysis` preserves `ranked_root_causes`.
- Postgres payload tests assert stored RCA candidates win over path fallback.
- Feedback tests assert `root_cause_candidate` is accepted.
- TEP provider tests assert selector-scoped matching and no unscoped leakage.

### 7. Wrong vs Correct

Wrong:

```python
payload["ranked_root_causes"] = ranked_root_causes_from_paths(case_id, paths)
```

Correct:

```python
payload["ranked_root_causes"] = (
    stored_ranked_root_causes
    or ranked_root_causes_from_paths(case_id, paths)
)
```

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

## Scenario: RCA-Oriented KG Construction Build Contract

### 1. Scope / Trigger

Use this when changing source-to-KG construction stages, artifact manifests,
construction service DTOs, review queue behavior, or CLI/API build signatures.
This contract is cross-layer: scripts, service handlers, KG Studio, CSV import,
and RCA reasoning all consume these build artifacts.

### 2. Signatures

- CLI:
  `uv run python scripts/build_source_kg.py [--source-library PATH] [--toy-generic-structured-source] [--toy-generic-document-source] [--tep-semantic-lift-dir DIR] [--tep-variable-mapping PATH] [--tep-rca-graph-dir DIR] [--run-id ID] --output-dir DIR`
- Review CLI:
  `uv run python scripts/review_source_kg.py --build-dir DIR --action accept|reject [--item-type edge|ITEM_TYPE] --target-key TARGET_KEY`
- Review replay CLI:
  `uv run python scripts/replay_source_kg_reviews.py --build-dir DIR [--run-id ID]`
- Acceptance smoke CLI:
  `uv run python scripts/smoke_rca_kg_construction.py --output-dir DIR [--tep-kg-root TEP_KG_ROOT] [--require-tep] [--overwrite]`
- Service build source types:
  `structured_records`, `manual_table`, `tep_semantic_lift`,
  `tep_variable_mapping`, `tep_rca_graph`
- Service review queue:
  `GET /api/kg/construction/builds/{run_id}/review-queue`
- Service review action:
  `POST /api/kg/construction/builds/{run_id}/review`
- Required artifact keys:
  `nodes`, `edges`, `published_nodes`, `published_edges`,
  `source_library_manifest`, `draft_manifest`, `source_audit_graph_manifest`,
  `semantic_layer_manifest`, `rca_view_manifest`, `review_queue`,
  `review_decisions`, `publish_manifest`, `publish_report`, `summary`,
  `manifest`

### 3. Contracts

- Construction stages are:
  Source Library -> Parser / Chunk -> Extractor Registry -> Draft KG ->
  Entity Alignment -> Source Audit Graph -> Semantic Layer ->
  RCA Reasoning View -> Review Queue -> Versioned Publish manifest.
- `ParsedSourceContent` is the current ParserOutput contract. The pipeline
  resolves extractors first, parses sources once, and prefers
  `extract_from_parsed(parsed, source=...)` when an extractor supports it.
  Legacy `extract(source)` remains allowed for source-reference importers.
- Offline document IE may replay source-grounded fixtures for tests and local
  demos, but fixture/LLM output is still DraftKG candidate output with
  `review_status=auto`, not reviewed KG truth.
- Source Library manifests passed by `--source-library` are loaded through
  `load_source_library(...)`; relative source paths resolve from the manifest
  directory before parsing or extraction.
- Every build writes `source_library_manifest.json` before downstream layer
  manifests, and this artifact must not include inline source text or row
  values.
- `kg_construction_summary.json` and `kg_construction_manifest.json` must share
  the same stable artifact keys for all required outputs.
- `review_decisions.jsonl` is the append-only review decision log.
- `published_nodes.csv`, `published_edges.csv`, and `publish_report.json` are
  derived from candidate rows plus review decisions and publish policy.
- High-risk causal/root-cause, propagation, LLM/document, and low-confidence
  edges stay pending unless accepted. Rejected edges are excluded from published
  snapshots. Low-risk structured support edges may publish only with an explicit
  `policy_allowed` disposition in `publish_report.json`.
- The summary must include `kg_build_id`, `source_ids`,
  `extractor_versions`, `profile_version`, and `review_policy`.
- `source_audit_graph_manifest.json` must include `parsed_sources` summaries
  with parser kind, row count, chunk count, safe source metadata, and parser
  metadata. It must not include row values or full document text.
- `review_queue.json` items must include `target_key`, `item_type`,
  `priority`, `reason`, `review_status`, `candidate_payload`, `source`,
  `evidence`, `confidence`, `scenario`, `relation_family`, `graph_impact`,
  and `recommended_action`.
- Service review queues prefer `review_queue.json` when present and fall back
  to `edges.csv` for legacy builds.
- `POST /review` and `scripts/review_source_kg.py` accept edge and non-edge
  review queue items. Edge decisions update `edges.csv` status/counters,
  refresh the matching `review_queue.json` candidate payload, append the
  decision to `review_decisions.jsonl`, and refresh published snapshot
  artifacts. Non-edge decisions append the same decision log and synchronize the
  matching `review_queue.json` item without publishing alignment decisions as KG
  facts.
- API and CLI review actions must delegate to a reusable workflow under
  `src/kgtracevis/workflows/`, not duplicate artifact mutation logic.
- Review replay must rebuild from `source_library_manifest.json` plus
  `review_decisions.jsonl` rather than patching stale CSV rows. Accepted
  alignment decisions may override canonical IDs; rejected merge decisions keep
  the source entity split from the proposed canonical. Replay refreshes layer,
  queue, publish, summary, and construction manifest artifacts while preserving
  the append-only decision log.
- TEP RCA graph imports are source-backed candidates. TEP_KG `accept` does not
  become KGTraceVis `reviewed` automatically.
- Acceptance smoke must build the toy generic path from a Source Library
  manifest and must only run the TEP path when explicit TEP_KG artifact paths
  are supplied or required.
- External IDs belong in the alignment manifest canonical table by default.
  Only source-backed mapping rows should materialize explicit `ALIGNS_TO`
  draft relations, such as TEP variable mapping aliases.

### 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| Unsupported source type | fail before parser execution with missing extractor error |
| Structured/manual source has path | parser summary records row count and columns only |
| Document/text source has text | parser summary records chunk IDs/ranges only, not text |
| TEP semantic/RCA source has metadata paths | parser summary records source-reference path metadata |
| Required artifact exists beside legacy manifest but key is absent | service registry discovers the conventional filename |
| Legacy `edges.csv` lacks optional RCA columns | service review code fills optional columns as blanks |
| `review_queue.json` contains alignment items | service DTO parses them and keeps `review_status=auto` filters working |
| Candidate edge is accepted/rejected | edge CSV and queue payload counters stay synchronized |
| Non-edge review item is accepted/rejected | queue payload and decision log update, but KG CSV rows are not republished as reviewed facts |
| Review replay lacks source_library_manifest.json | fail with a deterministic source reconstruction error |

### 5. Good/Base/Bad Cases

- Good: toy generic CLI build writes every required artifact and records
  `kg_build_id`, extractor versions, profile version, and review policy.
- Good: TEP build imports semantic lift, variable mapping, and RCA graph
  artifacts while preserving `relation_family`, propagation flags, and
  FaultAnchor/root-candidate metadata.
- Base: old build directories with only `nodes.csv`, `edges.csv`, and
  `kg_construction_manifest.json` remain readable through fallback paths.
- Bad: parser audit stores a source document chunk's full text in the manifest.
- Bad: automatic external ID alignment creates hundreds of `ALIGNS_TO` edges
  that are later skipped by semantic projection.

### 6. Tests Required

- Construction workflow tests assert all required artifacts exist and share
  artifact keys in summary and manifest.
- CLI tests cover toy generic builds, TEP semantic/RCA graph builds, and
  deterministic `--run-id` metadata.
- Alignment tests assert canonical table, merge candidates, unresolved
  entities, and conflicts survive JSON round trip.
- Review queue tests assert high-risk causal edges, merge candidates,
  unresolved entities, and alignment conflicts are prioritized.
- Service tests assert build response/registry/detail expose all artifact paths
  and queue filtering works for both edge and alignment items.
- Parser audit tests assert row values and full document text are not written
  into `source_audit_graph_manifest.json`.

### 7. Wrong vs Correct

#### Wrong

```python
artifact_paths = {"nodes": output_dir / "nodes.csv"}
```

#### Correct

```python
artifact_paths = kg_construction_artifact_paths(output_dir)
```

#### Wrong

```text
TEP_KG review_status=accept -> KGTraceVis review_status=reviewed
```

#### Correct

```text
TEP_KG review_status=accept -> DraftRelation(status="auto")
human/API review -> KGTraceVis review_status=reviewed
```

#### Wrong

```text
source_audit_graph_manifest.parsed_sources[*].chunks[*].text
```

#### Correct

```text
source_audit_graph_manifest.parsed_sources[*].parser_metadata.chunk_char_ranges
```

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
