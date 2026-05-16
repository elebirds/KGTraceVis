# implement: complete document understanding mode iteration

## Goal

Complete the next iteration of KGTraceVis Document Understanding Mode for RCA-oriented source KG construction: verify the existing scaffold, close functional gaps, preserve default chunk compatibility, add targeted tests, and ensure long-context / agentic document understanding remains planning/context/review material rather than a direct KG authority.

## What I already know

* The previous `05-15-document-understanding-mode` task has been archived.
* Recent commits include `fbd2478 Add document understanding mode scaffold`.
* The working tree was clean at session start.
* User explicitly requested subagent usage and iterative completion.
* Required safety boundary: long-context / agentic outputs must not bypass DraftKG, review queue, publish snapshot, or overlay validation semantics.

## Assumptions

* The repository already contains a first scaffold; this task should complete missing integration and tests rather than redesign from scratch.
* No external network dependency should be required for tests; offline fixtures should cover LLM-like behavior.
* Default `document_understanding_mode="chunk"` must remain backward compatible.

## Requirements

* Inspect current scaffold and identify remaining gaps.
* Ensure document understanding artifacts are generated and wired through manifests/diffs where expected.
* Ensure chunk IE prompt context uses document map hints without relaxing current-chunk evidence grounding.
* Ensure cross-chunk proposals require sufficient source spans, enter review, and never auto-publish.
* Add/repair tests for default compatibility, long_context artifacts, prompt context, proposal rejection/review, diff coverage, and overlay validation preservation.
* Run focused tests first, then broader test suite if feasible.

## Acceptance Criteria

* [x] Default chunk mode remains compatible.
* [x] Long-context mode generates document map artifacts.
* [x] Document map context improves alias/abbreviation prompt context while evidence remains current-chunk grounded.
* [x] Cross-chunk proposal without enough spans is rejected.
* [x] Valid cross-chunk proposal enters review queue and not published edges.
* [x] KG construction diff records document map / cross-chunk proposal artifact changes.
* [x] Overlay validation still requires `overlay_contributed=true`.
* [x] TEP and material_direct smoke paths do not regress.

## Definition of Done

* Tests added/updated.
* Focused tests pass.
* Broader regression command run or explicitly reported if blocked.
* No direct LLM publication path introduced.
* Task notes updated with implementation summary.

## Out of Scope

* Live external LLM calls in tests.
* Direct Neo4j publish from document understanding.
* Training or model fine-tuning.

## Technical Notes

* Implemented `chunk_prompt_context.jsonl` generation for non-chunk document
  understanding modes in material extraction.
* Added construction-level document understanding artifacts:
  `document_understanding_manifest.json`, `document_map.json`,
  `chunk_prompt_context.jsonl`, and `cross_chunk_proposals.jsonl`.
* Added cross-chunk proposal validation: relation whitelist, head/tail presence,
  conservative confidence cap, and at least two supporting spans.
* Valid cross-chunk proposals become `cross_chunk_relation_candidate` review
  items; rejected proposals remain in the proposal artifact and do not enter
  publish output.
* Extended construction artifact diff snapshots to include document
  understanding manifest, document map, chunk prompt context, and cross-chunk
  proposals.
* Added tests for long_context/agentic document map + prompt context artifact
  propagation and cross-chunk proposal review/publish/diff behavior.
* Verification passed:
  `uv run --extra dev pytest` -> 353 passed.
* Verification passed:
  `uv run python scripts/run_examples.py` -> 4 examples validated.
* Verification passed:
  `uv run --extra dev ruff check .`.
* Verification passed:
  `uv run --extra dev mypy src tests scripts`.
* Polish pass added first-class construction artifact fields for
  `document_understanding_manifest`, `document_map`, `chunk_prompt_context`,
  and `cross_chunk_proposals` through service DTOs, material direct-build
  responses, workflow results, frontend contracts, and API tests.
* Code-spec updated:
  `.trellis/spec/backend/database-guidelines.md` now documents the document
  understanding artifact/review/publish boundary.
* Final verification passed after polish:
  `uv run --extra dev pytest` -> 354 passed.
* Final verification passed after polish:
  `uv run --extra dev ruff check .`.
* Final verification passed after polish:
  `uv run --extra dev mypy src tests scripts`.
* Final verification passed after polish:
  `npm run typecheck` from `web/`.
* Final verification passed after polish:
  `uv run python scripts/run_examples.py` -> 4 examples validated.
* Final verification passed after polish:
  `git diff --check`.

## Polish Notes

* Updated document-understanding docs to describe current cross-chunk proposal
  behavior: proposals require allowed relations, endpoints, and at least two
  supporting spans; valid proposals enter review and never publish directly.
* Added API/service contract coverage for `chunk_prompt_context_path` so the
  extraction route returns both document map and prompt-context artifact paths.
* Updated construction artifact-key tests to follow
  `KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS`, keeping document-understanding
  artifacts in the required artifact contract.
