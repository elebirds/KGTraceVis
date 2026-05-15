# brainstorm: artifact review workflow for RCA KG

## Goal

Expose the review/publish loop as a reusable artifact workflow and CLI, so a
local reviewer can build a candidate RCA-KG, inspect review targets, accept or
reject an edge, and refresh the published snapshot without running the API
service.

## What I already know

* M3 added `review_decisions.jsonl`, `published_nodes.csv`,
  `published_edges.csv`, and `publish_report.json`.
* Service review currently owns most artifact mutation logic.
* Project rules say scripts and services should call reusable workflows instead
  of duplicating core logic.
* The next practical user path is no-key offline document build -> review
  decision -> published snapshot -> dry-run import.

## Requirements

* Add reusable workflow logic under `src/kgtracevis/workflows/`.
* Support edge accept/reject by `target_key` or edge parts.
* Append review decisions to `review_decisions.jsonl`.
* Refresh `edges.csv`, `review_queue.json`, `kg_construction_summary.json`,
  `kg_construction_manifest.json`, and published snapshot artifacts.
* Add a CLI that points at a build output directory and applies one decision.
* Keep service review route behavior compatible by delegating to the workflow.

## Acceptance Criteria

* [x] CLI can accept an offline document causal edge and produce one reviewed
  published edge.
* [x] Reusable workflow and service route share the same review mutation logic.
* [x] Review decision JSONL contains the applied decision.
* [x] Publish report changes from `pending_review` to `accepted`.
* [x] Existing service tests continue passing.

## Implementation Notes

* Added `src/kgtracevis/workflows/kg_construction_review.py` as the shared
  artifact review workflow.
* Added `scripts/review_source_kg.py` for service-free edge accept/reject.
* Service edge review now delegates to the reusable workflow.
* Removed stale service-local review mutation helpers.
* Added workflow and CLI tests for accepting an offline document causal edge and
  refreshing the published snapshot.
* Verification: focused review workflow, service, and construction workflow
  tests `46 passed`; focused ruff and mypy checks passed.

## Definition of Done

* Focused workflow/CLI/service tests pass.
* Full `uv run --extra dev pytest` passes.
* `uv run python scripts/run_examples.py` passes.
* `uv run --extra dev ruff check .` passes.
* `uv run --extra dev mypy src tests scripts` passes.

## Out of Scope

* Frontend review UI.
* Non-edge alignment/entity decision application.
* Neo4j write execution.

## Technical Notes

* Relevant specs read: backend workflow architecture, RCA KG construction build
  contract, error handling, quality guidelines.
