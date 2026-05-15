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

`Parser / Chunk` turns sources into extractor inputs: rows, text chunks, structured records, or source references. Parsers do not emit final KG facts.

`Extractor Registry` maps source types to extractor plugins. All extractors emit `DraftKG`. LLM document IE is isolated as one extractor type and cannot publish facts.

`Draft KG` is the unified intermediate layer for `DraftEntity`, `DraftRelation`, optional alignments, signal mappings, and RCA hints. Auto-generated rows default to `draft` or `auto`, not reviewed.

`Entity Alignment` performs deterministic ID, alias, external ID, and mapping-table alignment. High-risk merges should remain candidates or conflicts for review.

`Source Audit Graph` preserves the full provenance-rich extraction state for debug and drill-down. It is not the default RCA runtime graph.

`Semantic Layer` projects aligned drafts through a domain profile. It keeps task-relevant labels, rewrites relations, and assigns relation families.

`RCA Reasoning View` annotates the semantic layer with RCA metadata: `relation_family`, `propagation_enabled`, `propagation_direction`, `propagation_priority`, `attenuation`, `edge_weight`, root/observable flags, task view, confidence policy, and `kg_build_id`.

`Review Queue` prioritizes candidates that need human attention, especially causal/root-cause edges, low-confidence propagation edges, new anchors, merge conflicts, and facts that can affect Top-K RCA paths.

`Versioned Publish` prepares build metadata for runtime publication. Neo4j remains the runtime KG target; CSV/JSON artifacts are reproducible experiment snapshots.

## Domain Packs

Domain behavior lives in RCA profiles under `kgtracevis.kg_construction.profiles`.

The `generic` profile includes relation families:

```text
OBSERVATION, CAUSES, AFFECTS, DEPENDS_ON, PART_OF, ALIGNS_TO
```

The `tep` profile includes relation families:

```text
OBSERVATION, CONTROL, MATERIAL_FLOW, ENERGY_TRANSFER, PHASE_CHANGE,
COMPOSITION, FAULT_SOURCE, ALIGNMENT
```

Profiles own label keep-lists, relation whitelists, relation rewrites, propagation families, root candidate labels, observable labels, task view names, and confidence policy.

## LLM Boundary

LLMs may extract source-grounded candidate entities and relations from documents, propose aliases, summarize review items, explain conflicts, or generate RCA path explanation text.

LLMs must not directly publish KG facts, decide canonical IDs, decide propagation direction, overwrite reviewed facts, train edge weights, or replace RCA ranking algorithms. LLM output stays in DraftKG with source evidence and `auto` review status.

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
draft_manifest.json
source_audit_graph_manifest.json
semantic_layer_manifest.json
rca_view_manifest.json
review_queue.json
publish_manifest.json
kg_construction_summary.json
kg_construction_manifest.json
```

`kg_construction_summary.json` and `kg_construction_manifest.json` share the same
artifact path contract. The required artifact keys are:

```text
nodes
edges
draft_manifest
source_audit_graph_manifest
semantic_layer_manifest
rca_view_manifest
review_queue
publish_manifest
summary
manifest
```

The summary explicitly records `kg_build_id`, `source_ids`,
`extractor_versions`, `profile_version`, and `review_policy`. The publish
manifest records the same version boundary plus counts so downstream Neo4j
publication and RCA reasoning runs can reference a reproducible build snapshot.

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

```bash
uv run python scripts/build_source_kg.py \
  --tep-semantic-lift-dir /Users/hhm/code/TEP_KG/data/processed/kg \
  --tep-variable-mapping /Users/hhm/code/TEP_KG/data/processed/kg/tep_variable_mapping.jsonl \
  --tep-rca-graph-dir /Users/hhm/code/TEP_KG/data/processed/rca \
  --output-dir runs/source_kg_build/tep_rca_candidate \
  --overwrite
```

The resulting `nodes.csv` and `edges.csv` are an RCA view snapshot, not proof that all imported TEP facts are reviewed industrial truth.
