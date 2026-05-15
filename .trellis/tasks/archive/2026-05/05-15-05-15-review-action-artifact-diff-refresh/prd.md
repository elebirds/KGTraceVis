# M13 review action artifact diff refresh

## Goal

Refresh `kg_construction_diff.json` immediately when a construction review
action mutates artifacts, so operators can inspect the impact of accept/reject
without first running review replay.

## Requirements

* Edge review actions snapshot artifacts before mutation and after mutation.
* Non-edge review item actions snapshot artifacts before mutation and after
  mutation.
* The refreshed diff includes the review decision provenance and uses a scope
  that distinguishes direct review actions from replay.
* Review workflow result objects and CLI output expose `diff_path`.
* Existing replay behavior remains unchanged.

## Acceptance Criteria

* [ ] Accepting an edge refreshes `kg_construction_diff.json` with changed edge,
      review queue, summary, and publish report information.
* [ ] Reviewing a non-edge alignment item refreshes `kg_construction_diff.json`
      with changed review queue/summary information.
* [ ] `scripts/review_source_kg.py` prints `diff_path`.
* [ ] Focused review workflow tests pass, then full quality gate passes.

## Out of Scope

* Persisting historical per-decision diff files.
* UI rendering for diffs.
