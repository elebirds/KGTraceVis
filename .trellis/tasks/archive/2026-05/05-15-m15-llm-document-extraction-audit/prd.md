# M15: Productize LLM Document Extraction Audit

## Goal

Strengthen the KG construction material extraction path so LLM document IE is visibly a bounded candidate-generation adapter, not the final product experience. A material extraction run should leave reviewable, replayable audit artifacts that explain parser/chunking inputs, prompt/version policy, chunk-level IE outcomes, and candidate record counts before any KG build or publish step consumes the output.

## What I Already Know

* The current document extraction boundary is clear in code: `DocumentIEClient` emits source-grounded candidates and all output becomes `DraftKG`.
* The material service currently writes `structured_records.jsonl`, saves full source chunks, and records one extraction run row.
* The current product gap is auditability: API/service responses do not expose a manifest, prompt version, chunk count, chunk-level status, or extraction artifacts beyond structured records.
* LLM outputs must remain `auto`/candidate facts, never reviewed or published facts.
* Existing acceptance smoke already covers zero-to-RCA KG builds for toy, direct material, and optional TEP paths.

## Assumptions

* This task should remain source-compatible with existing material extraction tests while adding new response fields.
* The manifest should avoid duplicating full source text; full text remains in the source chunk store where it is intentionally auditable.
* Chunk-level extraction should support future partial-failure UX, but the default behavior should stay fail-fast unless explicitly requested.

## Requirements

* Add a prompt/policy version constant for document IE and record it in prompts and extraction metadata.
* Add a chunk-level extraction report API in `kg_construction.document_extraction` without changing the fact that extractors return `DraftKG`.
* Material extraction must write:
  * `structured_records.jsonl`
  * `chunk_extraction_results.jsonl`
  * `extraction_manifest.json`
* Material extraction state and API response must expose manifest path, chunk results path, chunk count, error count, and prompt version.
* Extraction run metadata and artifact registry must include all extraction artifacts.
* Manifest/chunk-result artifacts must preserve provenance and counts without treating LLM output as reviewed facts.

## Acceptance Criteria

* [x] Unit tests cover chunk-level extraction summaries and prompt versioning.
* [x] Material extraction tests verify manifest/chunk-result artifacts and response fields.
* [x] Runtime material store tests verify extraction artifacts are registered, not only structured records.
* [x] Full quality gate passes: ruff, mypy, pytest, examples.

## Definition of Done

* Tests added/updated.
* Lint, typecheck, tests, and example script pass.
* Trellis task is updated/archived and changes are committed.

## Out of Scope

* Building a full human review UI for document extraction.
* Letting LLM extraction publish KG rows directly.
* Making offline fixtures a first-class public extraction provider.
* Adding new database migrations beyond JSON payload fields already supported by material store tables.

## Technical Notes

* Main files: `src/kgtracevis/kg_construction/document_extraction.py`, `src/kgtracevis/service/kg_materials.py`.
* Related tests: `tests/test_kg_document_extraction.py`, `tests/test_kg_materials_service.py`.
* Spec constraints: backend/database KG construction helper rules require source/evidence/confidence and no automatic overwrite of reviewed facts.

## Implementation Notes

* Added `DocumentIEExtractionResult` and chunk summaries while preserving the existing `DraftKG` return interface for extractors.
* Material extraction now writes `structured_records.jsonl`, `chunk_extraction_results.jsonl`, and `extraction_manifest.json`.
* The manifest records prompt version, parser/chunk parameters, relation whitelist, candidate counts, and a clear LLM boundary without duplicating full source text.
* Updated docs and backend spec to make the product boundary explicit: document IE is one adapter inside the construction workspace, not the final KG product.
