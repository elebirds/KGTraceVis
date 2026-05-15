# M17: Auditable Alignment Layer

## Goal

Upgrade entity alignment from an internal canonicalization step into an auditable
construction layer. Deterministic merges should still canonicalize endpoints,
but the alignment stage should also emit source-backed `ALIGNS_TO` candidate
relations and a standalone alignment manifest artifact so users can inspect
what was aligned, why, and what still needs review.

## What I Already Know

* `run_entity_alignment(...)` already builds canonical entity table rows,
  merge candidates, unresolved records, and conflicts.
* `alignment_relations=()` is currently always empty.
* Existing review queue already surfaces merge candidates, unresolved entities,
  and conflicts.
* Existing TEP variable mappings emit explicit `ALIGNS_TO` draft relations from
  the TEP extractor; this task should not turn TEP_KG schema into global schema.
* Source audit graph embeds the alignment manifest, but there is no standalone
  alignment artifact.

## Assumptions

* Deterministic high-confidence exact self IDs should not generate noisy
  self-`ALIGNS_TO` relations.
* Generic alignment relations should be audit-layer candidates, not runtime RCA
  propagation edges.
* Explicit TEP variable-mapping `ALIGNS_TO` edges stay in the normal draft/semantic
  path; generic alignment relations are separate source-audit artifacts.

## Requirements

* Populate `AlignmentResult.alignment_relations` for non-trivial deterministic
  merges/overrides where `source_entity_id != canonical_id`.
* Include JSON-friendly alignment relation rows in `AlignmentResult.manifest()`.
* Write a standalone `entity_alignment_manifest.json` layer artifact.
* Include the alignment manifest in summaries, construction manifests, service
  responses, and diff snapshots.
* Keep review queue behavior for merge candidates/conflicts/unresolved entities.
* Add tests for materialized alignment relations and artifact export.

## Acceptance Criteria

* [x] Alignment manifest reports nonzero `alignment_relation_count` for alias/name
  merges.
* [x] Alignment relations preserve source/evidence/confidence and `ALIGNMENT`
  metadata.
* [x] Source workflow writes `entity_alignment_manifest.json`.
* [x] Existing TEP smoke remains stable.
* [x] Full quality gate passes.

## Definition of Done

* Tests added/updated.
* Lint, typecheck, tests, examples, and RCA construction smoke pass.
* Trellis task is archived and changes are committed.

## Out of Scope

* LLM-assisted merge decisions.
* Fuzzy/embedding alignment.
* Publishing alignment relations into runtime RCA `edges.csv`.
* Full alignment review UI.

## Technical Notes

* Main files: `alignment.py`, `pipeline.py`, `models.py`,
  `workflows/source_kg_construction.py`, service response DTOs.
* Tests: `tests/test_kg_construction_pipeline.py`,
  `tests/test_source_kg_construction_workflow.py`, service API path tests.

## Implementation Notes

* Added audit-layer `alignment_relations` for nontrivial deterministic
  canonicalization, surfaced only through `entity_alignment_manifest.json`.
* Added `alignment_manifest` to the required construction artifact contract,
  summary/manifest output maps, artifact diff snapshots, service DTOs, direct
  material build responses, and smoke validation.
* Preserved TEP explicit `ALIGNS_TO` extractor behavior in runtime edges while
  keeping generic alignment relations out of `alignment.draft.relations`.
* Added regression coverage for provenance fields (`source`, `evidence`,
  `confidence`, `review_status`) and service/material artifact exposure.
