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

Completed construction builds can be inspected and validated before any future
publish step:

```http
GET /api/kg/construction/builds
GET /api/kg/construction/builds/{run_id}
POST /api/kg/construction/builds/{run_id}/validate
POST /api/kg/construction/builds/{run_id}/review
POST /api/kg/construction/builds/{run_id}/publish
```

The registry is file-backed in v0. It scans `runs/source_kg_build/*` for
`kg_construction_manifest.json`, returns artifact paths and summary counts, and
runs structured KG CSV QA on the selected build. Validation is read-only and
does not import to Neo4j.

The review endpoint is the pre-publish control point for candidate edges. It
updates only the selected construction build's `edges.csv` and manifest. A
review target can be identified by the stable edge key
`head|relation|tail|scenario`:

```json
{
  "target_key": "ApiManualSource|BELONGS_TO|ApiManualTarget|tep",
  "action": "accept",
  "reviewer": "operator-a",
  "note": "source-backed relation"
}
```

`accept` sets `review_status=reviewed` and increments the accepted feedback
counter. `reject` sets `review_status=rejected` and increments the rejected
feedback counter. Both actions append a review decision to
`kg_construction_manifest.json`. The endpoint does not publish to Neo4j.

The publish endpoint is also safe-by-default. Calling it with an empty JSON body
performs a dry-run import count over the default seed KG plus the selected
candidate build:

```json
{}
```

To inspect only the candidate overlay, pass:

```json
{"include_defaults": false}
```

Real Neo4j writes require both `{"dry_run": false}` and
`{"confirm_publish": true}` in the request body. This keeps exploratory
candidate knowledge explicit: publication writes source, evidence, confidence,
and review status into Neo4j, but it does not turn `auto` rows into reviewed or
verified facts.

Source files can also be staged through the backend before a build:

```http
POST /api/kg/construction/sources/upload
GET /api/kg/construction/sources
```

The upload endpoint stores single-file `manual_table`, `structured_records`, or
`tep_variable_mapping` artifacts under `runs/source_kg_sources/` and returns a
build-ready `KGConstructionSourceInput`. Multi-file TEP semantic-lift bundles
still require explicit local node/edge paths in v0.

The maintained React workbench exposes this local workflow in KG Studio's
`Build` tab. That page composes the same API-safe request shapes, displays the
resulting artifact paths and summary manifest, and refreshes KG Studio so the
candidate graph can be inspected in the existing `Graph`, `Review`, and
`Draft Lab` tabs.

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
