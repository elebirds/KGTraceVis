# brainstorm: document understanding mode for source KG construction

## Goal

Add a Document Understanding Mode to KGTraceVis source KG construction so long-context or agentic document reading can provide document-level planning, terminology, alias, and cross-chunk hints while preserving the existing source-grounded chunk IE, DraftKG, review, publish, diff, and overlay validation boundaries.

## What I already know

* Existing KG construction flow includes Source/Material, Parser/Chunk, Extractor Registry, DraftKG, Entity Alignment, Source Audit Graph, Semantic Layer, RCA Reasoning View, Review Queue, Publish Snapshot, and Runtime Overlay Validation.
* Current smoke paths include toy_generic, material_direct, runtime_overlay, tep, and tep_runtime_overlay.
* Current tests are reported at 348 passed.
* TEP candidate KG construction is expected to remain stable around 173 nodes, 285 edges, 159 propagation edges, 63 fault-source edges, and 16 fault anchors.
* Overlay validation must only report validated when contract_validated, runtime_validated, and overlay_contributed are all true.
* Current LLM document extraction is chunk-based and must remain a candidate extractor, not a KG authority.
* Long-context / agentic outputs must be planning/context/hints unless transformed into reviewed, source-grounded DraftKG candidates.

## Assumptions (temporary)

* The first milestone should preserve default `chunk` behavior byte-for-byte or close enough that current smoke/tests do not regress.
* `long_context` should be introduced behind explicit configuration and endpoint/CLI flags.
* `agentic` can initially share most data contracts with `long_context`, with a deterministic/non-LLM scaffold where no external LLM is configured.
* Cross-chunk relation candidates should enter review artifacts and diffs, not publish snapshots.

## Open Questions

* None blocking for initial code research and design.

## Requirements (evolving)

* Add `document_understanding_mode` with at least `chunk`, `long_context`, and `agentic`.
* Generate document map artifacts containing parser/chunk metadata, section outline, glossary, entity inventory, relation hints, ontology/profile suggestions, unresolved questions, and review hints.
* Inject document map context into chunk IE prompts without relaxing strict current-chunk evidence requirements.
* Support cross-chunk proposal artifacts with conservative confidence, high review priority, explicit span requirements, and no auto-publish path.
* Extend review/diff/material extraction artifacts so document map and cross-chunk proposal changes are auditable.
* Preserve overlay validation semantics.

## Acceptance Criteria (evolving)

* [ ] Default chunk mode remains compatible and existing tests do not regress.
* [ ] Long-context mode can generate a document map artifact.
* [ ] Document map context can improve alias/abbreviation handling in chunk IE while evidence remains from the current chunk.
* [ ] Cross-chunk proposals without sufficient source spans are rejected.
* [ ] Cross-chunk proposals enter review queue but not published edges.
* [ ] KG construction diff records document map / cross-chunk proposal changes.
* [ ] Overlay validation still requires overlay_contributed=true before validated=true.
* [ ] TEP and material_direct smoke do not regress.

## Definition of Done (team quality bar)

* Tests added/updated for unit and smoke coverage.
* `uv run --extra dev pytest` passes.
* `uv run python scripts/run_examples.py` passes.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered because this touches KG construction and review/publish boundaries.

## Out of Scope (explicit)

* Direct LLM publication to final KG CSVs or Neo4j.
* Treating document-level summaries as facts without source evidence.
* Replacing chunk IE with long-context extraction.
* Training new models.

## Technical Notes

* Initial task created from user request on 2026-05-15.
* Current chunk IE center: `src/kgtracevis/kg_construction/document_extraction.py`.
  It defines `ParsedSourceDocument`, `SourceTextChunk`, `DocumentIEClient`,
  `OfflineDocumentIEFixtureClient`, prompt building, OpenAI-compatible calls,
  response schema coercion, strict evidence grounding, relation whitelist, and
  conversion to `DraftEntity` / `DraftRelation`.
* Material extraction entry point:
  `src/kgtracevis/service/kg_materials.py::extract_kg_material_to_structured_records`.
  It parses/chunks material, runs IE with report, writes
  `structured_records.jsonl`, `chunk_extraction_results.jsonl`, and
  `extraction_manifest.json`, then marks the material build-ready.
* Source construction workflow:
  `src/kgtracevis/workflows/source_kg_construction.py` materializes inline
  source text, runs `run_kg_construction`, writes source library, draft/profile/
  alignment/audit/semantic/RCA/review/publish artifacts, and writes a no-op
  construction diff for fresh builds.
* Core construction pipeline:
  `src/kgtracevis/kg_construction/pipeline.py` parses sources, selects
  extractors, combines DraftKG, aligns entities, builds source audit graph,
  projects semantic layer, builds RCA view, builds review queue, validates CSV,
  and produces publish manifests.
* Review queue:
  `src/kgtracevis/kg_construction/review_queue.py` currently handles edge and
  alignment item types through a generic `ReviewQueueItem`, so document-map and
  cross-chunk item types can reuse the DTO if the builder is generalized to
  accept extra items.
* Diff:
  `src/kgtracevis/kg_construction/artifact_diff.py` currently snapshots nodes,
  edges, review_queue, alignment/profile/semantic/RCA/publish/summary counts.
  It needs optional snapshots for document map and cross-chunk proposal
  artifacts.
* Artifact keys:
  `src/kgtracevis/kg_construction/models.py::KG_CONSTRUCTION_ARTIFACT_FILENAMES`
  is the central artifact key map. Service artifact lookup in
  `src/kgtracevis/service/kg_construction.py::_known_construction_artifact_key`
  delegates to those keys plus overlay validation.
* CLI:
  `scripts/build_source_kg.py` already supports toy/offline document source
  through source library or `--toy-generic-document-source`; material extraction
  does not yet have a dedicated CLI.
* Overlay validation:
  `src/kgtracevis/workflows/kg_overlay_validation.py` already implements the
  required `validated = contract_validated and runtime_validated and
  overlay_contributed` semantics.
* Current dirty files predate this task and must be preserved:
  `src/kgtracevis/kg_construction/document_extraction.py`,
  `src/kgtracevis/kg_construction/extractors/document_llm.py`,
  `src/kgtracevis/service/kg_materials.py`, and the m32 Trellis task.
