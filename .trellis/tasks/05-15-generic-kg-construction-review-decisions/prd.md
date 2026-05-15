# brainstorm: generic KG construction review decisions

## Goal

Extend KG construction review from edge-only accept/reject into a generic append-only review decision workflow that can record and synchronize decisions for alignment/review queue items such as merge candidates, unresolved entities, and conflicts.

## What I already know

* Edge review is already implemented in `src/kgtracevis/workflows/kg_construction_review.py` and exposed by `scripts/review_source_kg.py` plus the service route.
* Review queue items already include non-edge `item_type` values from alignment: `entity_merge_candidate`, `unresolved_entity`, and `entity_alignment_conflict`.
* Current edge workflow mutates `edges.csv`, refreshes `review_queue.json`, appends `review_decisions.jsonl`, updates summary/manifest, and refreshes published snapshots.
* Applying alignment decisions all the way through canonical remapping and RCA re-projection is larger than one clean slice.

## Requirements

* Add a reusable generic review workflow for any review queue item by `target_key` and `item_type`.
* Keep edge review behavior compatible by delegating edge items to the existing edge workflow.
* For non-edge review items, append `review_decisions.jsonl`, update the matching `review_queue.json` item status and candidate payload, and mirror decisions in summary/manifest.
* Add CLI support for non-edge review decisions without requiring edge head/relation/tail fields.
* Preserve append-only decision log as the source of truth.
* Do not treat accepted alignment decisions as automatically published KG facts in this slice.

## Acceptance Criteria

* [x] CLI can accept/reject a non-edge review queue item by `target_key` and `item_type`.
* [x] Non-edge decisions append to `review_decisions.jsonl` and manifest review decisions.
* [x] `review_queue.json` reflects the decision status and proposed payload for the target item.
* [x] Edge review path remains compatible and still refreshes publish snapshot artifacts.
* [x] Invalid target/item type combinations fail with deterministic `ValueError`.

## Implementation Notes

* Added generic `review_decision_for_item(...)` and
  `review_kg_construction_item_artifact(...)`.
* Kept edge decisions delegated to the existing edge artifact workflow, including
  `edges.csv` status updates and published snapshot refresh.
* Non-edge decisions update only `review_queue.json`, `review_decisions.jsonl`,
  summary decision counts, and construction manifest review decisions.
* Extended `scripts/review_source_kg.py` with `--item-type` and
  `--proposed-payload-json`.
* Extended the service review route to accept non-edge review queue items while
  keeping existing edge request shapes compatible.
* Updated RCA-KG architecture docs and Trellis construction review contract.
* Verification: focused review/service tests `7 passed`; construction/service
  slice `72 passed`; full pytest `321 passed`; `run_examples.py`, full ruff,
  and full mypy passed.

## Definition of Done

* Focused workflow/CLI/service tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for generic review decisions.

## Out of Scope

* Recomputing alignment canonical tables from accepted decisions.
* Rebuilding semantic/RCA views after non-edge decisions.
* Frontend review UI.
* Neo4j publishing.

## Technical Notes

* Relevant specs read: backend workflow architecture, RCA KG construction build contract, error handling, quality guidelines, shared cross-layer/code reuse guides.
