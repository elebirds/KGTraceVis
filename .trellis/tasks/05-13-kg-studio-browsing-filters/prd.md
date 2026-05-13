# Improve KG Studio Browsing And Filters

## Goal

Make KG Studio usable on larger candidate KGs by adding filtering and search to the route-backed workspace pages.

## Requirements

- Add one shared KG Studio filter bar for candidate edges:
  - text query across head/relation/tail/source/evidence,
  - scenario filter,
  - source filter,
  - review status filter,
  - reset action.
- Apply the shared edge filters to Graph, Review, and Draft Lab pages.
- Add source/document search to the Sources page.
- Preserve append-only review and draft behavior.
- Keep the layout readable at the current in-app browser width.
- Remove incidental duplicate JSX props introduced during the first KG Studio split.

## Acceptance Criteria

- [x] Graph edge browser can be filtered by query/scenario/source/review status.
- [x] Review queue and Draft target selector use the same filtered target set.
- [x] Sources and documents can be searched independently of edge filters.
- [x] Frontend build passes.
- [x] Browser verification confirms the filtered pages remain readable.

## Completion Notes

- Added a shared candidate-edge filter bar for Graph, Review, and Draft Lab.
- Added source/document search to Sources.
- Fixed incidental duplicate JSX props while wiring the filter state.
- Verified filter behavior in the browser with `Loc` and `wafer` searches.
