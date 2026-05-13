# KG Studio Workspace Refactor

## Goal

Turn KG Studio from one crowded mixed panel into a focused multi-page workspace that feels like a real system module for source management, graph inspection, review, and draft editing.

## Requirements

- Split KG Studio into route-backed subpages:
  - Overview: status, counts, validation, file paths, review progress.
  - Sources: source registry, source documents, source-to-KG draft generation.
  - Graph: large candidate KG graph plus edge browser and selected edge provenance.
  - Review: review queue, selected edge provenance, accept/reject/needs-review actions.
  - Draft Lab: selected edge and draft adjustment form.
- Keep the top-level KG Studio entry stable and redirect it to the overview.
- Avoid a three-column crowded layout.
- Preserve existing API contracts and append-only review/draft behavior.
- Keep long evidence/source/path text readable inside cards.
- Verify with browser screenshots and frontend build/tests.

## Acceptance Criteria

- [x] `/kg-studio` redirects or lands on an overview subpage.
- [x] `/kg-studio/sources`, `/kg-studio/graph`, `/kg-studio/review`, and `/kg-studio/drafts` render focused pages.
- [x] Existing KG Studio actions still work from the appropriate pages.
- [x] Frontend build passes.
- [x] Browser verification shows the KG Studio pages are not cramped.

## Completion Notes

- Extracted KG Studio UI into `web/src/KGStudioWorkspace.tsx`.
- Added route-backed Overview, Sources, Graph, Review, and Draft Lab views.
- Changed the graph preview to a selected-edge neighborhood view to reduce label clutter.
- Added shared frontend formatting helpers in `web/src/format.ts`.
- Updated dashboard docs to describe the KG Studio subpages.
