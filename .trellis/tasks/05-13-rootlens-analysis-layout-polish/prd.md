# RootLens Analysis Layout Polish

## Goal

Improve the Analysis module layout so it behaves like a coherent investigation
workspace rather than a set of loosely arranged cards.

## Requirements

- Keep the route-backed IA from the previous refactor.
- Make `/analysis/live` prioritize the upload workflow without squeezing it
  beside a secondary history panel.
- Keep recent/history context available as a compact status strip or secondary
  surface.
- Make `/analysis/history` feel like a lookup page with dense but readable run
  rows.
- Make `/analysis/:runId` keep the investigation stage selector compact so the
  selected stage canvas stays visually dominant.
- Avoid duplicating backend reasoning logic in the UI.

## Acceptance Criteria

- [x] Live Analysis uses a full-width primary upload surface.
- [x] Recent run context is still visible without taking a permanent sidebar.
- [x] Detail stage navigation is compact and does not dominate the viewport.
- [x] Candidate Paths stage remains easy to read after the layout change.
- [x] Typecheck/build and dashboard smoke pass.

## Completion Notes

- Replaced the Live two-column layout with a command strip, full-width upload
  surface, and compact recent-run rail below.
- Split upload inputs into primary evidence selection and secondary parameter
  panels.
- Added History search and dataset filtering.
- Changed Detail stage navigation to compact Ant Design navigation steps with
  horizontal overflow handling.

## Out of Scope

- Backend API changes.
- Full visual evidence rendering for images, masks, or wafer maps.
- KG Studio redesign.

## Technical Notes

- Main files: `web/src/App.tsx`, `web/src/styles.css`.
- Preserve existing upload, review, KG Studio, and run-detail API contracts.
