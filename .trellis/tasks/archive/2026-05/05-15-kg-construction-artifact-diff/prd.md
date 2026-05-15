# brainstorm: KG construction artifact diff

## Goal

Add deterministic artifact diffing for RCA-KG construction builds, so replay and future version comparisons can explain exactly which nodes, edges, review items, and layer summaries changed.

## What I already know

* M9 added replay from `source_library_manifest.json` and `review_decisions.jsonl`.
* Replay currently refreshes artifacts in place but does not capture a before/after explanation.
* Required final artifacts should include `kg_construction_diff.json`.
* Diff must be reusable and artifact-based; it should not depend on service or frontend state.

## Requirements

* Add `kg_construction_diff.json` to the construction artifact map.
* Write a no-op diff for fresh builds.
* During replay, snapshot current artifacts before rebuild, rebuild, snapshot after rebuild, and write a structured diff.
* Diff should cover at least nodes, edges, review queue items, semantic layer manifest, RCA view manifest, publish report, and summary counts.
* Include decision provenance from `review_decisions.jsonl` in the diff payload.
* Expose diff path in replay CLI output and docs/spec.

## Acceptance Criteria

* [ ] Fresh source-to-KG build writes `kg_construction_diff.json` with no changes.
* [ ] Replay after accepted merge records removed node/review item changes.
* [ ] Replay after rejected split records added/split node changes.
* [ ] Replay CLI output includes `diff_path`.
* [ ] Summary and construction manifest include `kg_construction_diff` artifact key.

## Definition of Done

* Focused diff/replay/workflow tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for the diff artifact.

## Out of Scope

* Visual graph diff UI.
* Semantic path-level RCA explanation diff beyond artifact row changes.
* Persisting historical artifact copies in this slice.

## Technical Notes

* Relevant specs read: backend workflow architecture and RCA KG construction artifact contract.
