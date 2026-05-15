# brainstorm: source material to RCA KG construction

## Goal

Enable KGTraceVis users to upload or register source materials, select materials for a build, and have the backend extract source-grounded candidate industrial KG entities and relations for RCA workflows. The system should turn papers, PDFs, webpages, manuals, and structured sources into reviewable KG artifacts without treating extracted triples as verified industrial facts by default.

## What I already know

* The target product direction is material upload/management plus user-selected source-to-KG construction for RCA-oriented industrial knowledge graphs.
* Existing KG construction is source-constrained and candidate-oriented, not an arbitrary-document extraction system.
* Current reusable construction core lives in `src/kgtracevis/kg_construction/pipeline.py`.
* Current runtime workflow lives in `src/kgtracevis/workflows/source_kg_construction.py`.
* Current API/service layer in `src/kgtracevis/service/kg_construction.py` supports source uploads, build listing, build detail, validation, review queues, review decisions, and dry-run/confirmed publish.
* Current source upload accepts single-file `manual_table`, `structured_records`, or `tep_variable_mapping` artifacts under `runs/source_kg_sources/`.
* Current build API intentionally accepts explicit structured/manual source records or explicit TEP semantic-lift / variable-mapping paths.
* Current docs explicitly say the API does not call live LLM extractors, parse source code, or publish automatically to Neo4j.
* The project rules require every KG edge to include `source`, `evidence`, `confidence`, and `review_status`.
* LLM output must be schema-validated, source-attached, confidence-scored, editable, and never treated as ground truth by default.

## Assumptions (temporary)

* The MVP should extend the existing candidate KG construction pipeline rather than replacing it.
* Extracted knowledge should land in the same `DraftKG` and KG CSV contract already used by construction builds.
* User-facing material management should preserve source provenance, extracted text chunks, and extraction status.
* The first useful version can be asynchronous or file-backed if it preserves a stable artifact contract.
* For webpages, URL registration plus backend fetch/snapshot may be sufficient for v0.
* For PDFs, local uploaded PDFs should be parsed into text chunks with page references before extraction.

## Open Questions

* Which MVP input class should we support first: PDFs, webpages, or both?

## Requirements (evolving)

* Users can upload or register source materials for KG construction.
* Users can list, inspect, and select stored materials for a construction build.
* The backend can parse selected materials into source-grounded text units with stable IDs.
* The backend can extract candidate entities and relations from parsed source units.
* Each extracted candidate relation includes source material ID, evidence text/span/page or URL context, confidence, and review status.
* Candidate outputs reuse the existing construction manifest, summary, review queue, validation, and publish flow where practical.
* Extraction must be RCA-oriented: relations should support evidence normalization, consistency checking, correction candidates, root-cause path ranking, visual explanation, or feedback review.
* The system must clearly label automatic extraction as candidate/reviewable knowledge.

## Acceptance Criteria (evolving)

* [ ] A material registry can persist and list uploaded/registered sources with metadata and processing status.
* [ ] A selected material build can produce `nodes.csv`, `edges.csv`, `kg_construction_summary.json`, and `kg_construction_manifest.json`.
* [ ] Extracted edges conform to the KG CSV contract and include source/evidence/confidence/review fields.
* [ ] Extracted candidate edges appear in the existing review queue and can be accepted or rejected.
* [ ] At least one automated document/web extraction path is covered by tests.
* [ ] The existing structured source build path continues to work.

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* Treating extracted causal relations as verified industrial truth.
* Building a giant general-purpose industrial KG.
* Overwriting reviewed KG triples automatically.
* Training a new deep extraction model.
* Publishing extracted KG rows to Neo4j without explicit validation/confirmation.

## Technical Notes

* Existing source-constrained pipeline: `src/kgtracevis/kg_construction/pipeline.py`.
* Existing source build workflow: `src/kgtracevis/workflows/source_kg_construction.py`.
* Existing service/API DTOs and handlers: `src/kgtracevis/service/kg_construction.py`.
* Existing lightweight source draft helper: `src/kgtracevis/service/kg_source_drafts.py`.
* Existing docs: `docs/kg_construction.md`, `docs/source_to_kg_construction_system.md`.
* Existing tests: `tests/test_kg_construction_pipeline.py`, `tests/test_source_kg_construction_workflow.py`, `tests/test_kg_source_drafts.py`.
* Current gap: material ingestion and extraction from unstructured PDF/web/text sources are not implemented as first-class construction sources.
* OpenAI-compatible extraction should use the optional `llm` extra and must be testable with a fake client; no tests should require network or API keys.
* Current OpenAI API docs still support Chat Completions with `response_format` JSON schema/JSON mode, while recommending Responses for new projects. For OpenAI-compatible providers, Chat Completions remains the broadest compatibility target.

## Parallel Implementation Plan

* Worker A owns `kg_construction/materials.py` and material-library unit tests.
* Worker B owns `kg_construction/document_extraction.py` and parser/LLM extraction unit tests.
* Worker C owns `service/kg_materials.py` and service DTO/handler tests.
* Worker D owns maintained frontend files in `web/` for KG Studio material management UI.
* Main session owns final route wiring in `service/api.py`, construction extractor registration, exports, integration tests, and verification.

## Planned MVP Architecture

```text
Material library
-> parse source material into stable source chunks
-> extract candidate entities/relations with fake/rule or OpenAI-compatible LLM
-> convert extracted candidates to DraftKG
-> run existing source-to-KG construction workflow
-> review queue / validate / publish reuse existing construction APIs
```
