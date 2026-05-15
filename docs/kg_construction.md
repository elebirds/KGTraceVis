# KG Construction

KG construction is source-constrained.

Candidate entities and triples may come from dataset labels, official tables,
curated project notes, SOP excerpts, or LLM-assisted extraction from provided
sources. LLM output is never treated as ground truth by default.

Each edge must keep its source, evidence text or row, confidence, weight, and
review status.

For the full source-to-KG methodology and future system design, see
[`source_to_kg_construction_system.md`](source_to_kg_construction_system.md).
For the new RCA-oriented generation architecture, domain pack boundary, TEP_KG
integration strategy, and layer manifests, see
[`rca_kg_generation_architecture.md`](rca_kg_generation_architecture.md).
For the current executable acceptance matrix and verification commands, see
[`rca_kg_construction_acceptance_matrix.md`](rca_kg_construction_acceptance_matrix.md).

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

For a single reusable validation report that covers runtime RCA consumption and
Neo4j import dry-run readiness, run:

```bash
uv run python scripts/validate_kg_overlay.py \
  --build-dir runs/source_kg_build/tep_candidate
```

This writes `kg_overlay_validation_report.json` beside the build. The report
records example-level linking/path counts, RCA path metadata such as
`path_strength`, `rca_score`, `source_edge_ids`, and `kg_build_ids`, plus the
merged import dry-run counts. It separates `contract_validated`,
`runtime_validated`, and `overlay_contributed`, so loading a candidate overlay
successfully is not confused with the overlay actually appearing in RCA paths.
If no top-k RCA path references the overlay `kg_build_id` or candidate edge ID,
the report sets `validated=false` and includes a
`missing_overlay_contribution_warning`. It does not rebuild KG artifacts,
review candidates, or publish anything.

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
counts, and artifact paths. Each fresh build also writes a no-op
`kg_construction_diff.json`; replaying review decisions refreshes that file with
before/after row and manifest changes plus the decision provenance. KG Studio
can inspect both legacy candidate directories (`nodes_candidate.csv` /
`edges_candidate.csv`) and these newer source-to-KG build directories
(`nodes.csv` / `edges.csv` plus the manifest).

The reusable runtime workflow lives in
`kgtracevis.workflows.source_kg_construction`. It is also exposed through the
local API:

```http
POST /api/kg/construction/build
```

The API intentionally accepts only explicit structured/manual source records or
explicit TEP semantic-lift / variable-mapping artifact paths. It writes the same
candidate `nodes.csv`, `edges.csv`, `entity_alignment_manifest.json`,
`kg_construction_summary.json`, and `kg_construction_manifest.json` files under
`runs/source_kg_build/<output_name>`.
It does not call live LLM extractors, parse source code, or publish to Neo4j.

Completed construction builds can be inspected and validated before any future
publish step:

```http
GET /api/kg/construction/builds
GET /api/kg/construction/builds/{run_id}
GET /api/kg/construction/builds/{run_id}/artifacts/{artifact_key}
POST /api/kg/construction/builds/{run_id}/validate
POST /api/kg/construction/builds/{run_id}/validate-overlay
GET /api/kg/construction/builds/{run_id}/review-queue
POST /api/kg/construction/builds/{run_id}/review
POST /api/kg/construction/builds/{run_id}/publish
```

The registry is file-backed in v0. It scans `runs/source_kg_build/*` for
`kg_construction_manifest.json`, returns artifact paths and summary counts, and
runs structured KG CSV QA on the selected build. Validation is read-only and
does not import to Neo4j.
The artifact endpoint serves one conventional construction artifact by stable
key, such as `nodes`, `review_queue`, `review_decisions`, or
`kg_construction_diff`, without accepting raw filesystem paths. After overlay
validation runs, the same endpoint can serve `kg_overlay_validation_report`.

`validate-overlay` runs the candidate build through the same reusable overlay
validation workflow as `scripts/validate_kg_overlay.py`. It writes
`kg_overlay_validation_report.json` beside the build and returns the report
payload, including runtime RCA path metadata, candidate contribution counts,
and import dry-run counts. It does not rebuild construction artifacts, record
review decisions, or publish to Neo4j.

Alignment is exported as its own audit layer. `entity_alignment_manifest.json`
contains canonical entity table rows, nontrivial deterministic `ALIGNS_TO`
candidate rows, merge candidates, unresolved entities, and conflicts. These
alignment rows document why endpoints were canonicalized, but they do not
become runtime RCA propagation edges unless an extractor emits an explicit
semantic relation.

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

The review queue endpoint is the read side of the same workflow. It returns
candidate edge rows with stable `target_key` values and can be filtered by
`review_status`, `source`, `scenario`, `relation`, and `query`, with `offset`
and `limit` pagination:

```http
GET /api/kg/construction/builds/kgbuild_demo/review-queue?review_status=auto&scenario=tep
```

The queue is read-only and exists to support backend review workflows and later
UI review pages without requiring clients to parse construction CSV files.

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

## Material Library And Document IE

The first material-library layer is available for source-grounded KG
construction inputs:

```http
GET /api/kg/materials
POST /api/kg/materials/upload
POST /api/kg/materials/register-url
POST /api/kg/materials/{material_id}/extract
POST /api/kg/materials/build-sources
POST /api/kg/materials/build
```

Uploads and URL registrations are stored under `runs/source_kg_materials/`.
They are provenance records only; registering a material does not mutate KG
artifacts and does not publish anything to Neo4j.

The extraction endpoint parses supported local material content into text
chunks, calls an OpenAI-compatible IE client, writes
`structured_records.jsonl`, `chunk_extraction_results.jsonl`, and
`extraction_manifest.json`, then updates the material's extraction metadata.
The manifest records parser/chunking settings, prompt version, extractor
version, the relation whitelist, chunk counts, error counts, and the explicit
claim boundary that LLM output is only candidate material. It stores chunk
locators and text hashes rather than duplicating the full source text; the
full parsed chunks stay in the source-chunk audit store. These records can then
be converted into an ordinary
`KGConstructionBuildRequest` through `POST /api/kg/materials/build-sources` and
passed to the existing source-to-KG build endpoint.
For pre-extracted materials, `POST /api/kg/materials/build` runs the reusable
material construction workflow directly and returns the artifact-complete build
payload, including `nodes.csv`, `edges.csv`, published snapshot paths,
`source_library_manifest.json`, layer manifests, `review_queue.json`,
`publish_manifest.json`, `publish_report.json`, and
`kg_construction_diff.json`. The direct route defaults to
`extraction_mode=never`, so it does not require an LLM key unless extraction is
explicitly requested.

The extractor is intentionally candidate-only. Each extracted relation keeps
source evidence, confidence, and `review_status=auto` after it enters the KG
CSV contract. Missing API keys, unavailable optional parsers such as `pypdf`,
ungrounded model evidence, invalid scenarios, or relation names outside the
RCA-oriented KG construction whitelist fail before a candidate build is
produced. Document IE also coerces model-returned entity references into the
same PascalCase-ish node ID style used by KG CSV validation.

The product boundary is therefore not "LLM returned triples". The product
experience is the audited construction workspace: source registration, parser
and chunk audit, source-grounded candidate generation, DraftKG conversion,
alignment/projection/review queues, and versioned build artifacts. The LLM is
one adapter inside that workspace and cannot skip review or publish.

Domain profile policy now controls more of the semantic/RCA shape. Profiles can
define semantic projection rules that rewrite a source relation and optionally
swap endpoints before the semantic layer is built. They also define
relation-family RCA defaults for propagation enablement, direction, priority,
attenuation, and edge-weight scaling. Source-backed extractor metadata still
wins when it explicitly supplies those RCA fields; otherwise the profile makes
the reasoning-view defaults reproducible across domains.

Profiles can now be loaded as JSON Domain Packs with `--profile-path` or the
workflow/service `profile_path` field. Each build writes
`profile_manifest.json`, recording the active profile source, ontology,
projection rules, relation-family policies, root candidate labels, and
observable labels. Built-in generic/TEP profiles remain the default when no
profile pack is supplied.

Profiles may also opt into conservative two-hop semantic derived-edge rules.
For example, a domain pack can derive `A -OBSERVED_BY-> C` from
`A -HAS_COMPONENT-> B` and `B -OBSERVED_BY-> C`. The derived edge remains
`review_status=auto`, cites both source-backed edge IDs in its evidence, and is
counted in `semantic_layer_manifest.json`.

RCA reasoning views now also write deterministic edge scoring components. The
profile relation-family policy controls the blend of confidence, propagation
priority, attenuation, and source trust. These values are exported as optional
RCA edge columns such as `rca_score`, `rca_score_confidence`,
`rca_score_priority`, `rca_score_attenuation`, and
`rca_score_source_trust`, while `rca_view_manifest.json` records the active
scoring policy and score summary.

The review queue consumes those RCA scores as prioritization hints. High-score
propagation edges and semantic-derived edges are surfaced with explicit graph
impact text and recommended actions, but they remain candidates until a review
decision accepts or rejects them.

Runtime path ranking also consumes RCA view score metadata when a candidate KG
overlay includes it. Path payloads expose `path_strength` and `rca_score`; when
those fields are absent on legacy seed KG edges, ranking falls back to the
existing confidence-based behavior. Paths and projected ranked root causes also
preserve `kg_build_ids` from supporting construction edges so an RCA result can
be traced back to the KG build snapshot it used.

The reusable orchestration entry point for this material-driven path is
`kgtracevis.workflows.material_kg_construction.run_material_kg_construction_workflow`.
It accepts selected material IDs, optionally extracts missing/selected materials
with an injected IE client, prepares build-ready construction sources, and then
calls the existing source-to-KG construction workflow. Material-driven builds
persist a `material_library` section in both `kg_construction_summary.json` and
`kg_construction_manifest.json`; that section records material IDs, source IDs,
extraction mode, extracted material IDs, material root, and the claim boundary.
The RCA-KG acceptance smoke also exercises this path with a pre-extracted
material fixture, so the no-key material workflow is checked alongside the toy
generic Source Library path and optional TEP_KG import path.

### Storage Boundary

Use the three storage layers for different jobs:

- Postgres stores workbench state: material metadata, source chunks, extraction
  runs, extraction artifacts, review/feedback records, and build history.
- Neo4j stores the published runtime KG used for graph queries and RCA path
  traversal.
- CSV/JSON/JSONL stores reproducible build artifacts such as `nodes.csv`,
  `edges.csv`, `structured_records.jsonl`, and construction manifests.

The material service now uses a runtime material-store provider. Passing an
explicit `material_root` keeps the file-backed adapter for local workflows and
tests. Without an explicit root, the default provider uses Postgres when a real
DSN is configured through `KGTRACE_POSTGRES_DSN`, `POSTGRES_*`, or
`configs/database.yaml`; otherwise it falls back to
`runs/source_kg_materials/`.

Even in Postgres-backed mode, uploaded bytes, URL snapshots, and
`structured_records.jsonl` stay on disk as reproducible artifacts. Postgres
stores the material records, parsed source chunks, extraction run metadata, and
artifact references that let the runtime workbench survive process restarts.

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
