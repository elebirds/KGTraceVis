# RootLens Path Graph Review Workspace

## Context

RootLens now has a clean dashboard foundation with upload modes, run history,
run detail, stable review targets, and a feedback smoke test. The next paper
need is to make traceability visible: a reviewer should be able to inspect a
candidate path, see which KG edges and sources support it, and submit review
feedback against stable path/edge/correction targets.

This task should stay foundation-oriented. It is not the full KG management
studio, not a force-directed graph editor, and not source+LLM KG generation.

## Goal

Add the first review workspace layer for RootLens:

- render candidate reasoning paths as a compact path graph instead of table-only
  text;
- expose source-edge provenance for the selected path/edge;
- group review targets into a queue that can drive the existing feedback form;
- preserve stable IDs/keys so future human-in-the-loop graph management can
  reuse feedback records.

## User Value

For the paper demo, this makes the system look like a visual analytics system
rather than a file runner. For engineering, it creates a clean bridge from
case-history analysis to later KG construction and manual KG adjustment.

## Requirements

### Backend/API

1. Keep reusable transformation logic under `src/kgtracevis/`.
2. If a path graph model is needed, add it as dashboard/service-friendly
   presentation data rather than duplicating KG reasoning.
3. Preserve existing API compatibility for `GET /api/runs/{run_id}` and feedback
   endpoints.
4. Do not mutate KG files from this task.
5. Include stable target references for path and edge review:
   - `target_type`
   - `target_id`
   - `target_key`
   - human-readable label/summary when available.

### Frontend

1. Add a Path Graph / Reasoning Workspace section to the run detail view.
2. Show candidate paths as compact node-edge chains with:
   - node labels,
   - relation labels,
   - score/confidence when available,
   - selected/hover/focus states.
3. Show provenance for the selected path or edge:
   - source,
   - evidence text,
   - confidence,
   - review status if available.
4. Add a review queue grouped by target type (`path`, `edge`, `correction`,
   `entity` where present) that can select the current feedback target.
5. Keep current upload/history/detail workflow intact.
6. Responsive behavior must remain usable on laptop-width and narrow screens.
7. Avoid adding a heavyweight graph dependency unless it materially reduces
   complexity; a deterministic SVG/HTML chain is acceptable for this foundation.

### Documentation

1. Update `docs/rootlens_dashboard.md` with the new review workspace behavior.
2. Update `README.md` only if launch or smoke instructions change.

### Smoke/Tests

1. Extend the existing dashboard smoke script to assert that uploaded example
   runs expose review targets and path/provenance data suitable for the UI.
2. Run frontend typecheck/build.
3. Run Python quality gates if backend, script, or test files change.

## Out of Scope

- Full KG force-directed editor.
- KG node/edge mutation or promotion into `data/kg/`.
- LLM source-to-KG extraction UI.
- Authentication or multi-user collaboration.
- Paper-grade user study instrumentation.

## Acceptance Criteria

1. A user can upload a checked-in example record/evidence file, open the run,
   and inspect at least one candidate reasoning path in a graph-like workspace.
2. Selecting a path/edge exposes source provenance and can drive the feedback
   target selection.
3. Empty/no-path cases show a useful empty state rather than broken UI.
4. The existing feedback form still writes stable target feedback.
5. Quality gates pass for touched layers.

