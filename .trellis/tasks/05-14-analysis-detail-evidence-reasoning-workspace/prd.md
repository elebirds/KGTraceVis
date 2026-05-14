# Analysis detail evidence-to-reasoning workspace polish

## Goal

Make Analysis Detail the main paper-demo stage for RootLens. A user should be
able to open a run/case and follow a clear flow from model evidence to KG
linking, consistency/correction, candidate paths, provenance, and review without
the page feeling like unrelated cards were stacked together.

## What I already know

- Analysis is the primary case-study surface for MVTec, WM811K, and future TEP.
- Existing `RunDetailView` already receives enough API data: run metadata,
  cases, generated evidence, visual evidence, linked entities, corrections,
  path graph, review targets, and artifacts.
- Current detail uses Steps, but each stage still feels like loose panels rather
  than a cohesive evidence-to-reasoning investigation.
- This task should remain frontend-only and keep current API contracts.

## Requirements

- Keep `/analysis/:runId` and the existing detail API contract.
- Improve the top case header into a compact case summary strip with:
  - run label/source;
  - case selector when multiple cases exist;
  - dataset/object/anomaly/prediction-style fields;
  - linked entity, correction, path, review target, and visual artifact counts.
- Reframe the timeline stages around the paper narrative:
  `Evidence -> Linking -> Consistency -> Candidate Paths -> Review`.
- Make visual evidence a focused, inspectable band with metadata instead of a
  competing equal-weight card.
- Make candidate paths use path list + selected path detail + provenance in one
  coherent workspace.
- Keep review controls tied to the currently selected review/path/edge target.
- Preserve empty states for runs with no visual evidence, no paths, no review
  targets, or no artifacts.
- Update dashboard docs for the new detail workspace behavior.

## Acceptance Criteria

- Web build succeeds.
- Existing Analysis/KG Studio/API tests pass.
- Browser verification covers a real local run detail page, case summary,
  visual evidence, candidate paths, and review controls.
- Project quality gates pass before commit.

## Out of Scope

- Backend API schema changes.
- New producer/model execution paths.
- New KG reasoning algorithms.
- Direct KG mutation from Analysis.

## Technical Notes

- Primary files: `web/src/App.tsx`, `web/src/styles.css`,
  `docs/rootlens_dashboard.md`.
- Reuse current `RunDetail`, `PathGraph`, `ReviewTarget`, and
  `VisualEvidenceItem` types.
