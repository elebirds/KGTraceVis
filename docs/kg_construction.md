# KG Construction

KG construction is source-constrained.

Candidate entities and triples may come from dataset labels, official tables,
curated project notes, SOP excerpts, or LLM-assisted extraction from provided
sources. LLM output is never treated as ground truth by default.

Each edge must keep its source, evidence text or row, confidence, weight, and
review status.

For the full source-to-KG methodology and future system design, see
[`source_to_kg_construction_system.md`](source_to_kg_construction_system.md).

## Construction Lifecycle

KGTraceVis treats KG construction as a reusable supply pipeline for the runtime
reasoning pipeline:

```text
source management
-> pluggable extraction
-> draft entities and relations
-> optional user review/editing
-> Neo4j publication
-> versioned KG consumed by KGTracePipeline
```

The current CSV files under `data/kg/` are seed and snapshot artifacts. The
runtime graph is imported into Neo4j for app and service queries, while CSVs
remain useful for reproducible examples, tests, and paper-facing exports.

## Source Types

Supported or planned source classes include:

- dataset labels and benchmark tables;
- adapter/model output records;
- mask geometry and wafer-map feature outputs;
- official papers and dataset documentation;
- manual curation tables;
- SOP/manual/log summaries;
- LLM-extracted candidates from provided text;
- future TEP/source-code files parsed by AST extractors.

All source types should converge to the same candidate entity/relation
intermediate representation before cleaning, review, and publication.

The reusable backend MVP is implemented under `src/kgtracevis/kg_construction/`:

- `draft.py` defines the draft KG intermediate representation;
- `extractors.py` defines the extractor protocol and registry;
- `models.py` defines construction run, draft-row, review-decision, summary,
  and manifest DTOs;
- `pipeline.py` runs registered extractors and validates KG rows;
- `tep_import.py` adapts TEP semantic-lift outputs into `scenario=tep` drafts.

Use the maintained CLI entry point to materialize candidate CSV artifacts:

```bash
uv run python scripts/build_source_kg.py \
  --tep-semantic-lift-dir /Users/hhm/code/TEP_KG/data/processed/kg \
  --tep-variable-mapping /Users/hhm/code/TEP_KG/outputs/kg/tep_variable_mapping.csv \
  --output-dir runs/source_kg_build/tep_candidate \
  --overwrite
```

Candidate CSVs can then be consumed as an overlay without changing the tracked
seed KG:

```bash
uv run python scripts/run_examples.py \
  --kg-node-path runs/source_kg_build/tep_candidate/nodes.csv \
  --kg-edge-path runs/source_kg_build/tep_candidate/edges.csv
```

Before publishing to Neo4j, validate the merged default KG plus candidate layer:

```bash
uv run python scripts/import_kg.py \
  --include-defaults \
  --nodes runs/source_kg_build/tep_candidate/nodes.csv \
  --edges runs/source_kg_build/tep_candidate/edges.csv \
  --dry-run
```

The same build writes `kg_construction_manifest.json`, which ties together the
construction run ID, source records, draft rows, reviewable KG payloads, summary
counts, and artifact paths. KG Studio can inspect both legacy candidate
directories (`nodes_candidate.csv` / `edges_candidate.csv`) and these newer
source-to-KG build directories (`nodes.csv` / `edges.csv` plus the manifest).

The reusable runtime workflow lives in
`kgtracevis.workflows.source_kg_construction`. It is also exposed through the
local API:

```http
POST /api/kg/construction/build
```

The API intentionally accepts only explicit structured/manual source records or
explicit TEP semantic-lift / variable-mapping artifact paths. It writes the same
candidate `nodes.csv`, `edges.csv`, `kg_construction_summary.json`, and
`kg_construction_manifest.json` files under `runs/source_kg_build/<output_name>`.
It does not call live LLM extractors, parse source code, or publish to Neo4j.

For TEP-specific graph construction, the external `TEP_KG` implementation should
be merged through extractor/import adapters rather than copied directly. See
[`tep_kg_merge_assessment.md`](tep_kg_merge_assessment.md) for the recommended
mapping from its `Full KG -> Semantic Lift Layer -> RCA Graph` approach into
KGTraceVis's source-to-KG pipeline.

## User Control

Review is recommended but not mandatory. Users may publish unreviewed candidate
knowledge for exploratory analysis, provided the resulting KG rows keep their
source, evidence, confidence, and review status.

Relation names should express semantics such as `CAUSES`, `AFFECTS`,
`HAS_MORPHOLOGY`, or `BELONGS_TO`. Trust should be expressed through
`confidence`, `review_status`, source provenance, and downstream reasoning
policies rather than by forcing duplicate weak relation names.
