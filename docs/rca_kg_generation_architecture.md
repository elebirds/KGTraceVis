# RCA-Oriented KG Generation Architecture

KGTraceVis KG construction is moving from a candidate CSV builder to an RCA-oriented KG generation system:

```text
Source Library
-> Parse / Chunk
-> Extractor Registry
-> Draft KG
-> Entity Alignment
-> Source Audit Graph
-> Semantic Layer
-> RCA Reasoning View
-> Review Queue
-> Versioned Publish
-> RCA Reasoning / Visualization / Feedback
```

The system is not a general industrial KG builder. It creates source-grounded, reviewable knowledge that can support evidence normalization, consistency checking, correction, RCA path ranking, visual analytics, and feedback.

## Layer Contracts

`Source Library` records material provenance. A source is not a KG fact. It may be a structured table, document, prior graph, variable mapping, code artifact, log/event file, manual table, or external project artifact such as TEP_KG outputs.

`Parser / Chunk` turns sources into extractor inputs: rows, text chunks,
structured records, or source references. Parsers do not emit final KG facts.
The construction pipeline runs the parser before extractor execution and keeps
an audit-safe parse summary in `source_audit_graph_manifest.json`. Structured
and manual table sources report row counts and columns. Text/document sources
report parser kind, chunk count, chunk IDs, and character ranges without storing
full source text. External/domain-pack sources such as TEP semantic-lift and RCA
graph artifacts report `source_reference` plus safe path metadata while leaving
extractor inputs unchanged.

`Extractor Registry` maps source types to extractor plugins. All extractors emit `DraftKG`. LLM document IE is isolated as one extractor type and cannot publish facts.

`Draft KG` is the unified intermediate layer for `DraftEntity`, `DraftRelation`, optional alignments, signal mappings, and RCA hints. Auto-generated rows default to `draft` or `auto`, not reviewed.

`Entity Alignment` performs deterministic ID, alias, external ID, and
mapping-table alignment. Its standalone `entity_alignment_manifest.json` is the
stable handoff for canonical entity table rows, source-backed audit-layer
`ALIGNS_TO` candidates, merge candidates, unresolved entities, and conflicts.
High-risk merges should remain candidates or conflicts for review. Alignment
relations are audit/provenance artifacts by default; they do not become RCA
runtime propagation edges unless a source extractor explicitly emits such a
semantic relation.

`Source Audit Graph` preserves the full provenance-rich extraction state for debug and drill-down. It is not the default RCA runtime graph.

`Semantic Layer` projects aligned drafts through a domain profile. It keeps
task-relevant labels, applies profile semantic projection rules, rewrites
relations, can swap endpoints when a source relation has the opposite
direction, and assigns relation families.

`RCA Reasoning View` annotates the semantic layer with RCA metadata:
`relation_family`, `propagation_enabled`, `propagation_direction`,
`propagation_priority`, `attenuation`, `edge_weight`, root/observable flags,
task view, confidence policy, and `kg_build_id`. Relation-family defaults now
come from the profile policy; extractor/import metadata may still override
those defaults when it is source-backed.

`Review Queue` prioritizes candidates that need human attention, especially causal/root-cause edges, low-confidence propagation edges, new anchors, merge candidates, unresolved entities, alignment conflicts, and facts that can affect Top-K RCA paths. Every item carries `review_status`, `priority`, `reason`, and `recommended_action`. Edge decisions can refresh the publish snapshot; non-edge alignment decisions are recorded and synchronized in the queue first, without automatically changing KG facts.

`Versioned Publish` prepares build metadata for runtime publication. Neo4j remains the runtime KG target; CSV/JSON artifacts are reproducible experiment snapshots.

## Domain Packs

Domain behavior lives in RCA profiles under `kgtracevis.kg_construction.profiles`.
Built-in generic and TEP profiles are available by default, and JSON Domain
Pack examples live under `configs/kg_construction/profiles/`. CLI and service
builds can select an external pack with `--profile-path` / `profile_path`; the
active pack is written to `profile_manifest.json` for reproducibility.

The `generic` profile includes relation families:

```text
OBSERVATION, CAUSES, AFFECTS, DEPENDS_ON, PART_OF, ALIGNS_TO
```

The `tep` profile includes relation families:

```text
OBSERVATION, CONTROL, MATERIAL_FLOW, ENERGY_TRANSFER, PHASE_CHANGE,
COMPOSITION, FAULT_SOURCE, ALIGNMENT
```

Profiles own label keep-lists, relation whitelists, semantic projection rules,
relation rewrites, relation-family RCA policies, root candidate labels,
observable labels, task view names, and confidence policy. A projection rule can
map a source relation to a semantic relation and optionally swap endpoints. A
relation-family policy defines whether propagation is enabled plus the default
direction, priority, attenuation, and edge-weight multiplier used by the RCA
reasoning view.

Profiles can opt into a deliberately small semantic derivation DSL: two-hop
rules that derive one relation from two existing semantic relations. Derived
edges are still source-backed candidates because their evidence cites the
source edge IDs used by the rule, and they are recorded in the semantic layer
manifest for audit.

Profiles also define the RCA scoring blend for each relation family:
confidence, propagation priority, attenuation, and source trust weights. The
reasoning view exports these as per-edge score components and summarizes them
in `rca_view_manifest.json`; this makes path ranking and visual explanations
inspectable without turning candidate edges into reviewed facts.

## LLM Boundary

LLMs may extract source-grounded candidate entities and relations from documents, propose aliases, summarize review items, explain conflicts, or generate RCA path explanation text.

LLMs must not directly publish KG facts, decide canonical IDs, decide propagation direction, overwrite reviewed facts, train edge weights, or replace RCA ranking algorithms. LLM output stays in DraftKG with source evidence and `auto` review status.

Document IE is deliberately not the final product experience. A live or fake
LLM call only fills candidate DraftKG rows. The user-facing construction
workspace must also expose the source library record, parser/chunk audit,
prompt/version policy, chunk-level extraction results, extraction manifest,
alignment/projection decisions, review queue, and versioned publish manifest.
The current material-library extraction endpoint writes
`structured_records.jsonl`, `chunk_extraction_results.jsonl`, and
`extraction_manifest.json` so reviewers can see what the model attempted before
those candidates enter RCA-KG construction.

## TEP_KG Integration

TEP_KG is treated as a strong TEP domain pack, not as the global schema.

The current import path uses:

```text
/Users/hhm/code/TEP_KG/data/processed/kg/semantic_lift_nodes.jsonl
/Users/hhm/code/TEP_KG/data/processed/kg/semantic_lift_edges.jsonl
/Users/hhm/code/TEP_KG/data/processed/kg/tep_variable_mapping.jsonl
/Users/hhm/code/TEP_KG/data/processed/rca/nodes.jsonl
/Users/hhm/code/TEP_KG/data/processed/rca/edges.jsonl
```

TEP import extractors preserve `relation_family`, `propagation_enabled`, external IDs, variable channels, RCA anchor roles, and source/provenance metadata. TEP `accept` review status is not automatically mapped to KGTraceVis `reviewed`; imported rows remain candidate `auto` unless reviewed or allowed by policy.

External IDs are retained in the alignment manifest's canonical entity table rather
than materialized as draft `ALIGNS_TO` edges by default. This avoids noisy
semantic-layer skips when an external identifier is provenance metadata rather
than a KG node. Source-backed mapping rows can still emit explicit `ALIGNS_TO`
draft relations; the TEP variable mapping extractor uses that path for
alternate variable IDs such as `variable:mv_42 -> variable:manipulated_variable_*`.

## Current Implementation Slice

The current Python structure is:

```text
src/kgtracevis/kg_construction/
  sources.py
  parsers.py
  extractors/
    base.py
    structured.py
    document_llm.py
    tep_import.py
  draft.py
  alignment.py
  audit_graph.py
  semantic_projection.py
  rca_view.py
  review_queue.py
  publish.py
  profiles.py
  pipeline.py
```

The workflow writes:

```text
nodes.csv
edges.csv
published_nodes.csv
published_edges.csv
source_library_manifest.json
draft_manifest.json
entity_alignment_manifest.json
source_audit_graph_manifest.json
semantic_layer_manifest.json
rca_view_manifest.json
review_queue.json
review_decisions.jsonl
publish_manifest.json
publish_report.json
kg_construction_diff.json
kg_construction_summary.json
kg_construction_manifest.json
```

`kg_construction_summary.json` and `kg_construction_manifest.json` share the same
artifact path contract. The required artifact keys are:

```text
nodes
edges
published_nodes
published_edges
source_library_manifest
draft_manifest
profile_manifest
alignment_manifest
source_audit_graph_manifest
semantic_layer_manifest
rca_view_manifest
review_queue
review_decisions
publish_manifest
publish_report
kg_construction_diff
summary
manifest
```

The summary explicitly records `kg_build_id`, `source_ids`,
`extractor_versions`, `profile_version`, and `review_policy`. The publish
manifest records the same version boundary plus counts so downstream Neo4j
publication and RCA reasoning runs can reference a reproducible build snapshot.
`review_decisions.jsonl` is the append-only human review log. `published_nodes.csv`,
`published_edges.csv`, and `publish_report.json` are the review-policy-controlled
runtime snapshot; high-risk causal, propagation, LLM/document, and low-confidence
edges stay out of that snapshot until accepted.
`kg_construction_diff.json` is a deterministic artifact-level diff. Fresh builds
write a no-op diff; review replay writes before/after changes for nodes, edges,
review queue items, semantic and RCA layer manifests, publish report, and summary
counts, including provenance from `review_decisions.jsonl`.
The source audit graph manifest additionally records `parsed_sources` entries
with `kind`, `parser_kind`, `row_count`, `chunk_count`, `source_reference`,
`safe_source`, and `parser_metadata`. These entries are summaries only; row
values and document text stay out of the manifest.

## ParserOutput And Offline Document IE

Source Library entries are represented by `SourceLibraryRecord` before parsing.
They include `source_id`, `source_type`, `scenario`, `path`/`url`/`text`,
metadata, `created_at`, and `provenance_policy`. JSON, JSONL, and CSV source
library files can be loaded into construction sources. When a Source Library is
loaded from a file, relative source paths resolve from the manifest directory so
the library can move as a portable bundle. Source-library manifests record only
safe descriptors such as IDs, paths, metadata, and `has_text`.

`ParsedSourceContent` is the current `ParserOutput` contract. The pipeline
resolves extractors first, parses each source once, and then prefers extractor
implementations with `extract_from_parsed(parsed, source=...)`. Older
`extract(source)` implementations remain supported for source-reference
importers such as TEP semantic lift and TEP RCA graph.

This makes the boundary explicit:

- parsers produce rows, text chunks, or source references;
- extractors produce only DraftKG candidates;
- audit manifests expose parser summaries, not full source text or raw row
  values;
- LLM and offline document IE outputs remain `auto` candidates and must pass
  evidence grounding before entering DraftKG.

For no-key development and regression tests, `OfflineDocumentIEExtractor`
replays a source-grounded fixture from `source.metadata["document_ie_payload"]`
or `source.metadata["document_ie_fixture_path"]`. It uses the same chunk-to-DraftKG
conversion and grounding checks as the LLM-backed extractor, but it never calls
an external model.

## Example Commands

Toy/manual structured sources can use the existing source construction workflow or API. TEP artifacts can be built from local TEP_KG outputs:

```bash
uv run python scripts/build_source_kg.py \
  --toy-generic-structured-source \
  --run-id kgbuild_toy_generic_demo \
  --output-dir runs/source_kg_build/toy_generic_candidate \
  --overwrite
```

The toy command writes a minimal generic structured source under `_sources/`
and emits the same CSV, layer manifest, publish manifest, summary, and
construction manifest files as larger builds.

An offline document-source smoke path is also available and does not require an
LLM key:

```bash
uv run python scripts/build_source_kg.py \
  --toy-generic-document-source \
  --run-id kgbuild_toy_document_demo \
  --output-dir runs/source_kg_build/toy_document_candidate \
  --overwrite
```

The document source creates a high-risk root-cause candidate, so
`published_edges.csv` remains empty until a reviewer accepts it.

User-provided Source Library manifests can drive the same build path:

```bash
uv run python scripts/build_source_kg.py \
  --source-library configs/source_library.json \
  --run-id kgbuild_source_library_demo \
  --output-dir runs/source_kg_build/source_library_candidate \
  --overwrite
```

The manifest may be JSON, JSONL, or CSV. Each entry becomes a
`KGConstructionSource`, and any relative `path` is interpreted relative to the
manifest file.

A local, service-free review can be applied with:

```bash
uv run python scripts/review_source_kg.py \
  --build-dir runs/source_kg_build/toy_document_candidate \
  --action accept \
  --target-key 'CoolingAlert|SUGGESTS_ROOT_CAUSE|PumpSealWear|shared' \
  --reviewer reviewer-id \
  --note 'source evidence checked'
```

This appends to `review_decisions.jsonl`, refreshes `review_queue.json`, and
rewrites the review-controlled `published_nodes.csv`, `published_edges.csv`,
and `publish_report.json` snapshot.

Non-edge review queue items use the same CLI with `--item-type` and a
`target_key` copied from `review_queue.json`:

```bash
uv run python scripts/review_source_kg.py \
  --build-dir runs/source_kg_build/source_library_candidate \
  --item-type entity_merge_candidate \
  --action accept \
  --target-key 'entity_merge_candidate:PumpB->PumpA' \
  --reviewer reviewer-id \
  --proposed-payload-json '{"reviewed_canonical_id":"PumpA"}'
```

This records the human decision and updates the queue item, but it does not
silently publish an alignment merge as reviewed KG truth.

To make accepted/rejected alignment decisions affect regenerated KG artifacts,
replay the build from its Source Library and decision log:

```bash
uv run python scripts/replay_source_kg_reviews.py \
  --build-dir runs/source_kg_build/source_library_candidate
```

Replay reruns Source Library -> Parse / Chunk -> Extractor Registry -> Draft KG
-> Entity Alignment -> Semantic Layer -> RCA View -> Review Queue -> Publish
using `review_decisions.jsonl` as an input. It refreshes artifacts in place
while preserving the decision log.

```bash
uv run python scripts/build_source_kg.py \
  --tep-semantic-lift-dir /Users/hhm/code/TEP_KG/data/processed/kg \
  --tep-variable-mapping /Users/hhm/code/TEP_KG/data/processed/kg/tep_variable_mapping.jsonl \
  --tep-rca-graph-dir /Users/hhm/code/TEP_KG/data/processed/rca \
  --output-dir runs/source_kg_build/tep_rca_candidate \
  --overwrite
```

The resulting `nodes.csv` and `edges.csv` are an RCA view snapshot, not proof that all imported TEP facts are reviewed industrial truth.

To run both acceptance paths through one command, use the smoke workflow. The
toy generic path always runs from a generated Source Library manifest. The TEP
path runs when a TEP_KG root is provided:

```bash
uv run python scripts/smoke_rca_kg_construction.py \
  --output-dir runs/source_kg_smoke \
  --tep-kg-root /Users/hhm/code/TEP_KG \
  --require-tep \
  --overwrite
```

The smoke summary checks that every required construction artifact exists for
each built path and that TEP RCA metadata such as `FAULT_SOURCE`,
`propagation_enabled`, and `FaultAnchor` survives the import.
