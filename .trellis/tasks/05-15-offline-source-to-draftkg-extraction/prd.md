# brainstorm: offline source to DraftKG extraction

## Goal

Move the RCA-KG construction pipeline from "parser metadata is audit-only" to a
real offline source-to-DraftKG path: sources are parsed once into a typed
ParserOutput, extractors consume that output through a common interface, and a
document extraction fixture can run without an LLM key while preserving the
LLM-as-adapter boundary.

## What I already know

* The previous refactor created the RCA construction spine:
  Source Library -> Parser / Chunk -> Extractor Registry -> Draft KG ->
  Entity Alignment -> Source Audit Graph -> Semantic Layer ->
  RCA Reasoning View -> Review Queue -> Versioned Publish.
* Current parser summaries are safe audit metadata, but extractors still mostly
  read the source files themselves.
* The next important gap is an offline/mock document IE path that demonstrates
  text chunks -> DraftKG -> review queue without requiring an LLM key.
* Structured and TEP import paths must continue to work, because they are the
  current verified smoke paths.

## Assumptions (temporary)

* This task should not introduce a real LLM provider or network dependency.
* ParserOutput should keep source content available in memory for extractors,
  while manifests continue to expose only safe summaries.
* Existing service/CLI artifact contracts should remain stable.

## Open Questions

* None blocking for the first implementation slice.

## Requirements (evolving)

* Introduce a reusable ParserOutput contract under `src/kgtracevis/kg_construction/`.
* Parse structured/manual/document/source-reference inputs once in the pipeline.
* Allow extractors to consume ParserOutput without breaking legacy source-based
  extractor implementations immediately.
* Add an offline document IE extractor fixture path that produces source-backed
  DraftKG rows from document chunks without an LLM key.
* Keep all automatic document extraction output as `auto`/reviewable DraftKG;
  never reviewed/published by default.
* Keep safe audit manifests free of full source text and row values.

## Acceptance Criteria (evolving)

* [x] A toy markdown/text source can build DraftKG, semantic layer, RCA view,
  and review queue without an LLM key.
* [x] Structured and TEP smoke paths keep passing with the stable artifact set.
* [x] Source audit manifests include parser summaries but not full document
  text or raw row values.
* [x] Tests cover parser-output-driven extraction and offline document IE.
* [x] Docs describe the offline extractor boundary and how it differs from real
  LLM extraction.

## Implementation Notes

* Added parser-aware extractor dispatch via `extract_source_draft(...)`.
* Added `extract_from_parsed(...)` paths for structured records and document IE.
* Added `extract_from_parsed(...)` for TEP variable mapping rows.
* Added `OfflineDocumentIEExtractor` for no-key replay fixtures.
* Added Source Library JSON/JSONL/CSV loading and safe manifest writing helpers.
* Added `--toy-generic-document-source` CLI smoke path.
* Curated Trellis implement/check context files for the M2 task.
* Verification: focused tests `30 passed`; full pytest `305 passed`;
  `run_examples.py`, ruff, and mypy passed.
* Additional focused verification: source library + pipeline tests `40 passed`.

## Definition of Done (team quality bar)

* Tests added/updated.
* `uv run --extra dev pytest` passes.
* `uv run python scripts/run_examples.py` passes.
* `uv run --extra dev ruff check .` passes.
* `uv run --extra dev mypy src tests scripts` passes.
* Docs/notes updated if behavior changes.

## Out of Scope (explicit)

* Real LLM API integration or key management.
* Neo4j publication beyond existing dry-run/import compatibility.
* Full Source Library UI or source lifecycle management.
* Rebuilding TEP_KG semantic lift from its raw source corpus.

## Technical Notes

* Relevant specs read: backend directory structure, database/KG construction
  contracts, workflow architecture, error handling, quality guidelines, shared
  cross-layer and code-reuse thinking guides.
* Main likely modules:
  `src/kgtracevis/kg_construction/parsers.py`,
  `src/kgtracevis/kg_construction/extractors/base.py`,
  `src/kgtracevis/kg_construction/extractors/structured.py`,
  `src/kgtracevis/kg_construction/extractors/document_llm.py`,
  `src/kgtracevis/kg_construction/pipeline.py`,
  `scripts/build_source_kg.py`, and construction tests.
