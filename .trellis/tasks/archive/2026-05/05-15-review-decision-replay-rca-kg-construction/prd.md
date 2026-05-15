# brainstorm: review decision replay for RCA KG construction

## Goal

Replay accepted/rejected non-edge review decisions back into the KG construction pipeline, so reviewed entity alignment choices can change the regenerated semantic layer, RCA view, review queue, and publish snapshot in a reproducible way.

## What I already know

* M8 added generic review decisions for non-edge queue items, but those decisions currently update only `review_decisions.jsonl`, summary/manifest, and `review_queue.json`.
* Entity alignment already emits merge candidates and unresolved/conflict records into `review_queue.json`.
* Construction builds now include `source_library_manifest.json`, so a build can be rerun from registered sources instead of trusting stale CSV artifacts.
* Existing workflow `run_source_kg_construction_workflow(...)` writes all required layer artifacts and publish artifacts.
* We need a conservative first replay slice that supports canonical override and split override without treating LLM or unreviewed candidates as facts.

## Requirements

* Add deterministic alignment review override logic for accepted/rejected non-edge review decisions.
* Accepted merge/unresolved/conflict decisions may supply `reviewed_canonical_id`, `canonical_id`, or `selected_canonical_id` to override a source entity's canonical ID.
* Rejected merge decisions should split the source entity away from the proposed canonical when possible.
* Add a reusable rebuild/replay workflow that loads sources from `source_library_manifest.json`, loads `review_decisions.jsonl`, reruns construction with alignment decisions, preserves review decisions, and refreshes all artifacts.
* Add CLI support to run replay for a build directory.
* Keep edge decisions/publish behavior compatible.
* Add focused tests for merge accept and merge reject replay.

## Acceptance Criteria

* [x] Accepted entity merge decision can replay into regenerated `nodes.csv` by collapsing the reviewed duplicate.
* [x] Rejected entity merge decision can replay into regenerated `nodes.csv` by keeping the reviewed duplicate split.
* [x] Replay refreshes semantic/RCA/review/publish artifacts and keeps `review_decisions.jsonl` append-only history.
* [x] CLI can run replay for an existing build directory and print a JSON summary.
* [x] Replay fails with a deterministic error if build sources cannot be reconstructed.

## Implementation Notes

* Added alignment review override support to `run_entity_alignment(...)`.
  Accepted non-edge decisions can provide `reviewed_canonical_id`,
  `selected_canonical_id`, or `canonical_id`; rejected merge decisions split the
  source entity from the proposed canonical.
* Added `review_decisions` input to `run_kg_construction(...)` and
  `run_source_kg_construction_workflow(...)`, so replay runs through the normal
  parser/extractor/alignment/projection/publish path instead of patching CSVs.
* Added `src/kgtracevis/workflows/kg_construction_replay.py` and
  `scripts/replay_source_kg_reviews.py`.
* Replay reconstructs sources from `source_library_manifest.json`, loads
  `review_decisions.jsonl`, preserves the decision log, and refreshes summary
  and construction manifest replay metadata.
* A reviewed split disambiguates same-name nodes with a canonical-id suffix so
  the existing node cleaner does not merge a human-rejected duplicate again.
* Updated RCA-KG docs and Trellis backend contracts with replay behavior.
* Verification: focused replay tests `4 passed`; construction/review/service
  slice `76 passed`; full pytest `325 passed`; `run_examples.py`, full ruff,
  and full mypy passed.

## Definition of Done

* Focused replay workflow/CLI tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for review decision replay.

## Out of Scope

* A full frontend conflict-resolution UI.
* Replaying arbitrary free-form graph edits.
* Neo4j write execution.
* LLM-assisted merge decisions.

## Technical Notes

* Relevant specs read: backend workflow architecture, RCA KG construction artifact/review contract, error handling, quality guidelines, shared cross-layer/code reuse guides.
