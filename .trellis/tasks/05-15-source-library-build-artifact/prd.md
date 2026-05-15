# brainstorm: source library build artifact

## Goal

Make the Source Library itself a first-class construction artifact for every RCA-KG build, so each output directory records the registered source set before parser/extractor stages.

## What I already know

* The target architecture starts with `Source Library` before Parse / Chunk.
* `write_source_library_manifest(...)` already writes an audit-safe Source Library manifest.
* `run_source_kg_construction_workflow(...)` currently writes draft, audit, semantic, RCA view, review, publish, summary, and construction manifest artifacts.
* `kg_construction_artifact_paths(...)` defines the shared artifact key map for summary, service, and review workflow discovery.
* Source text materialization already converts inline text into `_sources/<source_id>.*` before `run_kg_construction(...)`, so the final build source set can be represented as path-backed records.

## Requirements

* Add `source_library_manifest` to the shared KG construction artifact map.
* Write `source_library_manifest.json` for every `run_source_kg_construction_workflow(...)` build.
* Include the source library artifact key in `kg_construction_summary.json` and `kg_construction_manifest.json`.
* Ensure the manifest is audit-safe: no inline text or row/document contents.
* Update tests/docs/spec artifact contracts.

## Acceptance Criteria

* [x] Every source-to-KG build writes `source_library_manifest.json`.
* [x] Summary and construction manifest include `source_library_manifest` in their artifact maps.
* [x] Source Library manifest has source IDs, types, scenarios, paths/url/text flags, metadata, and provenance policy without leaking inline source text.
* [x] Existing review workflow continues to find and refresh required artifacts.

## Implementation Notes

* Added `source_library_manifest` to the shared construction artifact key map.
* Added `source_library_records_from_construction_sources(...)` and reused the
  existing `write_source_library_manifest(...)` writer.
* `run_source_kg_construction_workflow(...)` now writes
  `source_library_manifest.json` after text source materialization, so inline
  source payloads are represented by `_sources/...` paths rather than copied
  into the manifest.
* Service build responses and build registry records now expose
  `source_library_manifest_path`, with legacy fallback path discovery.
* Updated architecture docs and the Trellis KG construction artifact contract.
* Verification: focused artifact/service/review tests `11 passed`; full pytest
  `314 passed`; `run_examples.py`, full ruff, and full mypy passed.

## Definition of Done

* Focused source construction workflow and CLI tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for the expanded artifact contract.

## Out of Scope

* Service UI source browsing.
* Remote URL source fetching.
* Changing Source Library schema beyond artifact registration.

## Technical Notes

* Relevant specs read: backend workflow architecture, database/RCA KG construction contract, quality guidelines, shared cross-layer/code reuse guides.
