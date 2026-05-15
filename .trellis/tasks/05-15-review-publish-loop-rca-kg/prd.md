# brainstorm: review publish loop for RCA KG

## Goal

Turn RCA-KG construction output from "reviewable candidates only" into a
traceable human-review-controlled publish loop: append-only review decisions,
deterministic policy application, versioned publish snapshots, and reports that
explain why each candidate edge was published, skipped, rejected, or left
pending.

## What I already know

* The construction pipeline now produces DraftKG, alignment, semantic layer,
  RCA view, review queue, and publish manifest artifacts.
* Existing service review code can update `edges.csv` and `review_queue.json`,
  but review decisions are not yet a first-class append-only artifact.
* LLM/offline document IE and TEP imported RCA facts must remain candidates
  until human review or explicit low-risk policy allows publication.
* TEP_KG external `accept` status must not automatically become KGTraceVis
  `reviewed`.

## Assumptions

* Implement the first slice as reusable backend logic and workflow artifacts,
  not frontend UI.
* Keep existing construction artifact names stable and add new publish-loop
  artifacts rather than breaking old consumers.
* Policy defaults should be conservative: causal/propgation/LLM/document edges
  require review.

## Requirements

* Add an append-only review decision store/JSONL artifact for KG construction.
* Support decisions for edge review targets first, with DTOs flexible enough for
  entity/alignment items later.
* Apply review decisions and publish policy to candidate nodes/edges.
* Write a versioned publish snapshot with `published_nodes.csv`,
  `published_edges.csv`, and `publish_report.json`.
* Ensure accepted edges become `reviewed`, rejected edges are excluded, and
  policy-allowed low-risk edges may publish with an explicit policy reason.
* Ensure high-risk causal/document/propagation edges remain pending unless
  accepted.
* Add a no-key offline document example test: generated causal edge is pending,
  then accepted, then appears in the publish snapshot as reviewed.

## Acceptance Criteria

* [x] Review decisions are stored append-only and survive JSON round trip.
* [x] Publish policy produces counts for accepted, rejected, policy-allowed,
  pending, and skipped candidates.
* [x] Offline document causal edge is not published before acceptance.
* [x] Accepted offline document causal edge is published as `reviewed`.
* [x] TEP imported RCA graph edges remain candidates unless reviewed/policy
  allowed; external TEP status is preserved only as metadata.
* [x] Existing build artifacts and tests continue passing.

## Implementation Notes

* Added `review_decisions.jsonl`, `published_nodes.csv`,
  `published_edges.csv`, and `publish_report.json` construction artifacts.
* Added append/load review decision helpers and conservative publish policy in
  `kg_construction.publish`.
* Source construction workflow now writes an initial review-controlled publish
  snapshot.
* Service edge review appends decisions to JSONL, keeps legacy CSV/queue
  projections refreshed, and regenerates the publish snapshot.
* Service publish now reads `published_*.csv` when available instead of raw
  candidate CSVs.
* Verification: focused publish/service/workflow tests `9 passed`; construction
  pipeline/workflow/service tests `65 passed`; ruff and mypy focused checks
  passed. Offline document smoke emitted one pending candidate and zero
  published edges before review.
* Added focused TEP RCA graph assertion: imported external
  `review_status=accept` stays in draft metadata, while the propagated
  FAULT_SOURCE edge remains pending in publish policy until KGTraceVis review.

## Definition of Done

* Focused tests for review decisions and publish policy pass.
* Full `uv run --extra dev pytest` passes.
* `uv run python scripts/run_examples.py` passes.
* `uv run --extra dev ruff check .` passes.
* `uv run --extra dev mypy src tests scripts` passes.
* Docs/spec notes updated for the publish loop.

## Out of Scope

* Frontend review UI changes.
* Neo4j write/publish execution.
* Multi-user review locking.
* Full conflict resolution UI for entity merges.

## Technical Notes

* Relevant specs read: backend database/KG construction contract, workflow
  architecture, error handling, quality guidelines, shared thinking guides.
* Likely modules: `review_queue.py`, `publish.py`, `models.py`,
  `workflows/source_kg_construction.py`, `service/kg_construction.py`,
  `scripts/build_source_kg.py`, and construction tests.
