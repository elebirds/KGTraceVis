# KG Construction Review API

## Goal

Add a backend-only review action for source-to-KG construction builds so users
or future UI clients can accept or reject candidate KG edges before publishing
them to Neo4j.

## What I Already Know

- Construction builds already write `nodes.csv`, `edges.csv`,
  `kg_construction_summary.json`, and `kg_construction_manifest.json`.
- Edge rows already include `review_status`, `feedback_count`,
  `accepted_count`, and `rejected_count`.
- `kg_construction.models` already defines `KGConstructionReviewDecision` and
  `review_decision_for_edge`.
- Publish now defaults to dry-run and can include candidate overlays, but there
  is not yet a backend review action before publish.
- v0 should avoid a frontend implementation in this slice.

## Assumptions

- The first review API should focus on edge rows, because KG edge feedback is
  the trust boundary for source-constrained candidate knowledge.
- Node/entity review can be added later with the same decision log pattern.
- Review mutates the selected build artifact, not the tracked seed KG.

## Requirements

- Add `POST /api/kg/construction/builds/{run_id}/review`.
- Accept a stable edge target by either `target_key` (`head|relation|tail|scenario`)
  or explicit `head`, `relation`, `tail`, and `scenario`.
- Support at least `accept` and `reject`.
- `accept` sets `review_status=reviewed`, increments `feedback_count` and
  `accepted_count`.
- `reject` sets `review_status=rejected`, increments `feedback_count` and
  `rejected_count`.
- Append a `KGConstructionReviewDecision` entry to the construction manifest.
- Recompute summary `review_status_counts` after mutation.
- Return the updated edge, review decision, updated build record, and summary.
- Map unknown build IDs and edge targets to HTTP 404; invalid review requests
  should return HTTP 400/422.

## Acceptance Criteria

- [x] A built candidate edge can be accepted through the API and the CSV row is
  updated.
- [x] A built candidate edge can be rejected through the API and counters are
  updated.
- [x] The manifest records review decisions.
- [x] Unknown edge targets fail explicitly.
- [x] Docs describe the review endpoint as the pre-publish control point.

## Verification

- `uv run --extra dev ruff check src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py tests/test_service_api.py`
- `uv run --extra dev mypy src/kgtracevis/service/kg_construction.py src/kgtracevis/service/api.py`
- `uv run --extra dev pytest tests/test_service_api.py -q`
- `uv run --extra dev pytest -q`
- `uv run python scripts/import_kg.py --dry-run`
- `uv run python scripts/run_examples.py`

## Definition Of Done

- Tests added or updated.
- Lint, focused API tests, and full test suite pass.
- Documentation updated.
- Task archived and session journal recorded.

## Out Of Scope

- Frontend review controls.
- Node/entity review.
- Batch review.
- Confidence recalibration beyond deterministic review counters.
- Live Neo4j writes from the review endpoint.

## Technical Notes

- Expected service files: `src/kgtracevis/service/kg_construction.py` and
  `src/kgtracevis/service/api.py`.
- Expected tests: `tests/test_service_api.py`.
- Follow `.trellis/spec/backend/workflow-architecture.md` and
  `.trellis/spec/backend/error-handling.md`.
