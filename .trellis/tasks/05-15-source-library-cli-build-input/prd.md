# brainstorm: source library CLI build input

## Goal

Make `Source Library` manifests a first-class input to the RCA-KG construction CLI, so users can start a build from their own registered source set instead of relying only on toy flags or domain-specific arguments.

## What I already know

* The target architecture begins with `Source Library -> Parse / Chunk -> Extractor Registry -> Draft KG`.
* `src/kgtracevis/kg_construction/sources.py` already has `SourceLibraryRecord`, `load_source_library`, and `write_source_library_manifest`.
* `scripts/build_source_kg.py` currently supports toy structured/document sources and TEP-specific file/directory flags.
* Workflow logic already accepts a list of `KGConstructionSource` objects.
* Source library path values should be portable, so relative paths in a manifest should resolve relative to the manifest file.

## Assumptions

* This task should not introduce service upload behavior or a UI.
* JSON/JSONL/CSV source libraries are sufficient for the first CLI entry point.
* Existing toy and TEP CLI inputs should continue to work.

## Requirements

* Add `--source-library PATH` to `scripts/build_source_kg.py`.
* Load records with the reusable Source Library loader, then convert them to `KGConstructionSource` values.
* Resolve relative file paths in source library records relative to the library file directory.
* Keep source library metadata source-grounded and safe in manifests.
* Add focused tests for loader path resolution and CLI build from a source library.
* Update docs/spec signatures to mention the new input mode.

## Acceptance Criteria

* [x] CLI can build a toy offline document RCA-KG from a source library manifest.
* [x] Relative paths inside a source library manifest resolve from the manifest location.
* [x] Generated artifacts still include draft/semantic/RCA/review/publish manifests and summary.
* [x] Existing toy/TEP CLI behavior is not broken.

## Implementation Notes

* Added `--source-library PATH` to `scripts/build_source_kg.py`.
* Reused `load_source_library(...)` and `SourceLibraryRecord.to_construction_source()`
  instead of adding CLI-local source parsing.
* Updated `load_source_library(...)` so relative `path` values resolve from the
  source library file directory.
* Added loader and CLI regression tests covering portable document-source
  manifests with offline IE payloads.
* Updated RCA-KG architecture docs and the Trellis backend KG construction
  contract with the new CLI signature and relative-path behavior.
* Verification: focused source-library/CLI tests `5 passed`; construction suite
  slice `47 passed`; full pytest `314 passed`; `run_examples.py`, full ruff,
  and full mypy passed.

## Definition of Done

* Focused workflow/CLI/source-library tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for the new CLI contract.

## Out of Scope

* UI source library editor.
* Remote URL fetching for source libraries.
* Neo4j publish execution.
* LLM provider/key integration.

## Technical Notes

* Relevant specs read: backend workflow architecture, database/RCA KG construction build contract, error handling, quality guidelines, shared cross-layer and code reuse guides.
