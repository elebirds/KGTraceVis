# Add Case Selector To Analysis Detail

## Goal

Make multi-case record uploads usable by letting users inspect one concrete case
inside an Analysis detail run instead of only seeing aggregated links, paths, and
visual evidence.

## Requirements

- Preserve run-level history and summary.
- Add a case selector when a run contains multiple cases.
- Scope Model Evidence, Entity Linking, Consistency, Candidate Paths, and visual
  evidence to the selected case.
- Keep review target keys compatible with existing feedback.
- Preserve aggregate fallback behavior for single-case and older manifests.

## Acceptance Criteria

- [x] Multi-case records upload exposes a case selector in Analysis detail.
- [x] Selecting a case changes evidence fields, linked entities, paths, and
  visual evidence.
- [x] Per-case `path_graph` is available from the API for record-upload cases.
- [x] Existing single-case runs still render without a selector.
- [x] Quality gates pass.

## Completion Notes

- Added per-case `path_graph` and review targets for record-upload runs.
- Added a case selector in Analysis detail for multi-case runs.
- Scoped visual evidence, linked entities, corrections, path graph, and summary
  payloads to the selected case.
- Verified with `data/examples/records/mvtec_records.jsonl` in the web UI.

## Out Of Scope

- Deep comparison across cases.
- Bulk review workflow.
- Dataset/model changes.
