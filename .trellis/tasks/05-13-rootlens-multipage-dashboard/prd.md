# RootLens Multipage Dashboard IA

## Goal

Refactor the RootLens frontend from a single composite screen into a coherent
multi-page dashboard. The current functionality is useful, but the information
architecture feels like many unrelated panels stitched together. The next
version should look like a system: focused pages, navigation, and a clear path
from upload to analysis to KG management.

## Requirements

1. Add dashboard-level navigation with four focused pages:
   - Overview: system status, dataset/run/KG summary, quick next actions.
   - Intake: upload producer records/evidence/image and inspect run history.
   - Case Analysis: selected run detail, path graph, provenance, review queue.
   - KG Studio: source registry, source-to-KG draft, candidate graph, edge
     provenance, draft adjustments.
2. Preserve existing API contracts and workflow behavior.
3. Keep selected run and selected KG edge state across page switches.
4. Use hash routing or local state routing; do not add a full router dependency
   unless necessary.
5. Reduce visual clutter by showing only page-relevant controls on each page.
6. Keep responsive behavior usable on laptop and narrow widths.
7. Update docs to describe the page structure.
8. Verify frontend typecheck/build and dashboard smoke.

## Out of Scope

- Backend changes.
- Authentication.
- Full browser E2E framework.
- New KG functionality beyond layout/navigation.

## Acceptance Criteria

- [ ] Dashboard opens to an Overview page rather than a giant mixed workspace.
- [ ] Navigation switches between Overview, Intake, Case Analysis, and KG Studio.
- [ ] Upload/history is isolated to Intake.
- [ ] Case reasoning is isolated to Case Analysis.
- [ ] KG management is isolated to KG Studio.
- [ ] Existing smoke and quality checks pass.

