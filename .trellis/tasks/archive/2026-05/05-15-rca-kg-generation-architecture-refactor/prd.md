# brainstorm: RCA-oriented KG generation architecture refactor

## Goal

Refactor KGTraceVis KG construction into a source-grounded, review-controlled, RCA-oriented generation system. The target architecture is Source Library -> Parser / Chunk -> Extractor Registry -> Draft KG -> Entity Alignment -> Source Audit Graph -> Semantic Layer -> RCA Reasoning View -> Review Queue -> Versioned Publish -> RCA Reasoning / Visualization / Feedback.

## What I already know

* The new architecture must prioritize clarity over backward compatibility.
* Temporary breakage of old APIs, frontends, or tests is allowed while the new main path is established.
* Extractors must output DraftKG and must not directly publish reviewed/runtime facts.
* LLM extraction is one extractor type only, and all LLM output defaults to source-grounded draft/auto review status.
* TEP_KG should be integrated through domain pack extractors/profiles, not copied into the global schema.
* Final acceptance requires a toy generic RCA KG path and a TEP RCA KG path that produce draft, semantic, RCA view, review queue, and summary artifacts.
* Current KGTraceVis already has a usable source-to-KG spine: `DraftKG`, `KGConstructionSource`, `ExtractorRegistry`, `StructuredRecordExtractor`, `TepSemanticLiftExtractor`, `TepVariableMappingExtractor`, CSV export/QA, and a source workflow.
* Current gap: the pipeline jumps from extractor drafts directly to cleaned runtime CSV rows; alignment, source audit graph, semantic projection, RCA view, review priority, publish metadata, and per-layer manifests are not first-class stages.
* `/Users/hhm/code/TEP_KG` has usable local handoff artifacts: `data/processed/kg/semantic_lift_nodes.jsonl`, `semantic_lift_edges.jsonl`, `tep_variable_mapping.jsonl`, plus `data/processed/rca/nodes.jsonl` and `edges.jsonl`.

## Assumptions (temporary)

* The first implementation slice should create the new core data model and pipeline skeleton, then migrate existing extractors incrementally.
* Neo4j publish can remain a prepared interface until a later slice, as long as build metadata and artifact manifests are ready.
* Existing KG construction tests may need replacement or staged repair after the new architecture lands.

## Open Questions

* None blocking yet; repo inspection should determine the first viable implementation slice.

## Requirements (evolving)

* Introduce Source Library, parser/chunk, extractor registry, DraftKG, alignment, semantic projection, RCA view, review queue, versioned publish, and domain profile concepts under `src/kgtracevis/kg_construction/`.
* Add/extend draft models for entities, relations, alignments, signal mappings, and RCA hints.
* Extend runtime KG edges with RCA metadata such as relation family, propagation flags, direction, priority, attenuation, edge weight, task view, external edge id, and kg build id.
* Provide `generic` and `tep` RCA profiles.
* Preserve TEP metadata including relation family, propagation settings, anchors, and variable mappings.
* Add docs for the RCA KG generation architecture.

## Current Refactor Plan

### Keep

* `DraftKG`, `KGConstructionSource`, and extractor registry as the entry spine.
* `StructuredRecordExtractor` for deterministic table/JSON inputs.
* `TepSemanticLiftExtractor` and `TepVariableMappingExtractor`, with TEP metadata preserved.
* CSV export/QA helpers and `run_source_kg_construction_workflow` as the CLI/API artifact boundary.

### Rename / Move

* Move `extractors.py` into `kg_construction/extractors/base.py` and `structured.py`.
* Add `kg_construction/extractors/document_llm.py` as a wrapper boundary for document IE, keeping LLM output candidate-only.
* Keep TEP import code under `tep_import.py` for now, but expose TEP extractors through `kg_construction/extractors/tep_import.py` to match the target architecture.
* Treat `triple_cleaner.py` as a compatibility row normalizer; later rename to `row_normalizer.py`.

### Migrate Later

* `candidate_entity_extractor.py` and `candidate_triple_extractor.py` can be retired after draft-to-row conversion no longer needs the legacy bridge types.
* `case_kg_hardening.py` and `end_to_end_interpretability_audit.py` should move toward paper/experiment-specific workflows rather than generic RCA-KG construction.
* `material_kg_construction.py` should stop importing service functions directly in a later service-boundary cleanup.

### Delete Later

* Remove duplicate source-text draft helpers once structured parsing has a single owner.
* Remove legacy candidate overlay naming after KG Studio/service callers are migrated.

## Implementation Slice 1

* Introduce source parsing, domain profiles, deterministic alignment, semantic projection, RCA view construction, review queue scoring, publish manifest, and layer manifests.
* Extend `KGEdge` with optional RCA metadata while preserving old CSV loading.
* Add `TepRcaGraphExtractor`.
* Upgrade `run_kg_construction` and source workflow exports to write:
  `nodes.csv`, `edges.csv`, `draft_manifest.json`, `semantic_layer_manifest.json`,
  `rca_view_manifest.json`, `review_queue.json`, and `kg_construction_summary.json`.
* Add focused tests for a toy generic path and TEP semantic/RCA graph path.

## Implementation Notes

* Implemented the first architecture slice under `src/kgtracevis/kg_construction/`.
* Moved extractor registry into `kg_construction/extractors/` while preserving top-level re-exports.
* Added deterministic alignment that avoids silently merging different TEP labels sharing a human-readable name, e.g. `Stream` product vs `SignalNode` product.
* Added optional RCA edge columns while keeping existing KG CSV required columns loadable.
* Added workflow layer artifact output and CLI support for `--tep-rca-graph-dir`.
* Added `docs/rca_kg_generation_architecture.md`.

## Verification

* `uv run --extra dev pytest` passed: 290 tests.
* `uv run python scripts/run_examples.py` passed: 4 examples validated.
* `uv run --extra dev ruff check .` passed.
* `uv run --extra dev mypy src tests scripts` passed.
* `uv run python scripts/import_kg.py --dry-run` passed.
* TEP smoke build passed with local `/Users/hhm/code/TEP_KG` artifacts and wrote all required layer files to a temp output directory.

## Acceptance Criteria (evolving)

* [ ] Toy structured source builds DraftKG -> Alignment -> Semantic Layer -> RCA View -> Review Queue.
* [ ] TEP import reads `/Users/hhm/code/TEP_KG` semantic lift, variable mapping, and optional RCA graph artifacts into the same manifest/output structure.
* [ ] Outputs include `nodes.csv`, `edges.csv`, `draft_manifest.json`, `semantic_layer_manifest.json`, `rca_view_manifest.json`, `review_queue.json` or CSV, and `kg_construction_summary.json`.
* [ ] LLM/document IE remains isolated from core deterministic pipeline and cannot publish directly.
* [ ] New architecture is documented in `docs/rca_kg_generation_architecture.md`.

## Definition of Done (team quality bar)

* Tests added/updated for the new architecture path.
* `uv run --extra dev pytest` attempted.
* `uv run python scripts/run_examples.py` attempted or documented if temporarily incompatible.
* Docs/notes updated for changed construction architecture.
* Breakage of old paths is explicit and localized.

## Out of Scope (explicit)

* Full Neo4j runtime publishing implementation in the first slice.
* Treating TEP_KG as the global KGTraceVis schema.
* Direct LLM publishing or automatic overwrite of reviewed facts.

## Technical Notes

* Initial inspection requested by the user: `README.md`, `docs/kg_construction.md`, `docs/source_to_kg_construction_system.md`, `docs/tep_kg_merge_assessment.md`, `src/kgtracevis/kg_construction`, `workflows/source_kg_construction.py`, `workflows/material_kg_construction.py`, and `kg/graph.py`.
