# RootLens Dashboard Visual System Polish

## Goal

Make the RootLens frontend feel like a coherent visual analytics dashboard
rather than a functional but rough collection of panels. Keep the existing
workflows and API contracts, but introduce a product-grade app shell, navigation
menu, page headers, tab-like surfaces, toolbars, and a more disciplined visual
system.

## Decision

Do not use Figma as the primary path in this task. Figma/reference exploration
can help later, but the immediate issue is information hierarchy and component
language. Implement lightweight internal components first; avoid adding a large
UI framework unless needed.

## Requirements

1. Replace the top-only navigation with a dashboard app shell:
   - persistent sidebar menu;
   - top status/action bar;
   - main page canvas.
2. Add reusable visual primitives in the existing React file where practical:
   - sidebar/menu item pattern;
   - page header;
   - tab/segmented navigation styling;
   - metric/stat cards;
   - toolbar buttons.
3. Preserve the four-page IA:
   - Overview;
   - Intake;
   - Case Analysis;
   - KG Studio.
4. Improve visual quality without making it look like a marketing landing page:
   - restrained colors;
   - denser enterprise dashboard layout;
   - better spacing/typography;
   - clearer selected/focus states;
   - no decorative gradient blobs/orbs.
5. Keep mobile/narrow layout usable.
6. Do not change backend APIs.
7. Update docs if user-facing navigation changes.
8. Verify frontend typecheck/build, dashboard smoke, and core tests.

## Out of Scope

- Figma plugin integration.
- Full design-token package extraction.
- Rewriting the app with a UI framework.
- New feature behavior beyond visual shell and component polish.

## Acceptance Criteria

- [ ] Dashboard has a credible app shell with sidebar navigation.
- [ ] Pages have consistent headers and actions.
- [ ] Main workflows look like focused dashboard pages, not stitched panels.
- [ ] Visual state is clearer for selected page, selected path, and selected KG edge.
- [ ] Quality gates pass.

