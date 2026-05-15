# M29 Publish Report Decision Status Consistency

## Goal

Fix publish report rows so their `review_status` reflects review decisions when
publish disposition is driven by `review_decisions.jsonl`, not only by the
pre-mutated candidate edge CSV.

## Requirements

- Human `accept` decision over an `auto` candidate should report
  `disposition=accepted` and `review_status=reviewed`.
- Human `reject` decision over an `auto` candidate should report
  `disposition=rejected` and `review_status=rejected`.
- Existing edge CSV mutation/replay behavior must keep passing.

## Acceptance Criteria

- [ ] Focused publish tests cover decision-only accept/reject report statuses.
- [ ] Full quality gates pass.

## Out of Scope

- Changing publish policy.
- Changing review decision schema.
