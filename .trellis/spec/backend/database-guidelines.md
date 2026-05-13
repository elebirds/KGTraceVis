# Database Guidelines

KGTraceVis currently uses CSV-backed source-constrained KG files as the primary
development backend. Neo4j is supported as a future/import backend, but the v0
pipeline should remain runnable without a database service.

## Current Backends

| Backend | Purpose | Example |
|---|---|---|
| CSV files | tracked curated KG source of truth | `data/kg/nodes.csv`, `data/kg/edges.csv` |
| In-memory NetworkX graph | default analysis backend for tests/scripts/app | `KnowledgeGraph.from_default_paths()` |
| Neo4j | optional graph database import/query target | `scripts/import_kg.py` |

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

## Loading Pattern

Use `KnowledgeGraph.from_default_paths()` for the default development pipeline.
It loads the base KG plus development reference layers such as
`data/kg/mvtec_rca_reference.csv`.

Use `KnowledgeGraph.from_csv()` only when a test intentionally wants a single
node/edge CSV pair without reference layers.

Example:

```python
graph = KnowledgeGraph.from_default_paths()
result = KGTracePipeline(graph=graph).analyze(evidence)
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

## Neo4j Rules

Neo4j code should remain optional for v0:

- Do not make tests or scripts require a running Neo4j instance unless the script
  explicitly uses `--with-neo4j`.
- Keep CSV as the reproducible source of truth.
- Import scripts may read configs from `configs/neo4j.example.yaml` or
  environment variables.

## Common Mistakes

- Treating MVTec plausible RCA edges as verified factory root causes.
- Adding KG edges without `source`, `evidence`, `confidence`, or
  `review_status`.
- Putting generated experiment output into tracked KG CSV files.
- Requiring Neo4j for tests that should run against the in-memory graph.
