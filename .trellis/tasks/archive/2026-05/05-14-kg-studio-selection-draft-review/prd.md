# Tighten KG Studio selection and source draft review

## Goal

Make KG Studio feel safer for review work by keeping selected KG edges aligned
with the visible filtered result set and by presenting Source-to-KG generated
candidate edges as reviewable evidence rows instead of raw edge IDs.

## Requirements

- Graph, Review, and Draft Lab must share the same candidate-edge filters.
- If filters remove the currently selected edge, the workspace must move the
  selection to the first visible edge.
- Review and draft actions must be disabled when no filtered target is selected.
- Source-to-KG draft results must show candidate edge, scenario, confidence, and
  evidence in a table suitable for reviewer scanning.
- Documentation must describe the non-mutating workflow and the selection
  behavior.

## Acceptance Criteria

- `npm run build` succeeds for the web app.
- Focused KG Studio backend tests still pass.
- Browser verification covers filtered Graph/Review/Draft behavior and
  Source-to-KG draft result rendering.
- Generated KG artifacts remain untouched; this change is UI and documentation
  only.

## Out of Scope

- Full KG CSV mutation or promotion workflow.
- Remote LLM-backed source extraction.
- Reworking the backend KG construction pipeline.
