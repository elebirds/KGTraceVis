# RootLens Analysis Information Architecture Refactor

## Goal

Refactor the RootLens dashboard from a capability grid into a system-like
investigation platform. The top-level navigation should represent product
modules, while Analysis becomes a module with live analysis, historical case
lookup, and a timeline-driven detail view.

## Product Principles

- RootLens should feel like an investigation system, not a collection of cards.
- Top navigation should expose business domains, not implementation widgets.
- Heavy case content should not be forced into three permanent columns.
- Detail views should use a timeline/stepper so one evidence or reasoning stage
  owns the main canvas at a time.
- Review and provenance should stay close to the selected analysis item, but not
  crowd every stage by default.

## Target IA

Top-level modules:

1. Home
   - API/KG status
   - recent analyses
   - paper demo shortcuts
   - next actions
2. Analysis
   - Live: upload or run new evidence
   - History: searchable run/case list
   - Detail: selected run/case investigation timeline
3. KG Studio
   - sources
   - source-to-KG draft generation
   - candidate graph
   - edge provenance
   - review and draft adjustment
4. Experiments
   - paper case placeholders
   - KG coverage and before/after placeholders
   - export/report placeholders

## Implementation Scope

- Add route-backed navigation with `react-router-dom`.
- Keep existing API calls, reducer, upload, review, KG Studio, and smoke
  contracts intact.
- Replace state-only top page switching with routes:
  - `/`
  - `/analysis/live`
  - `/analysis/history`
  - `/analysis/:runId`
  - `/kg-studio`
  - `/experiments`
- Move current upload and run history into Analysis module pages.
- Replace current all-at-once `RunDetailView` with an investigation detail view
  using an Ant Design `Steps` timeline.
- Keep KG Studio as a module route, but leave deeper tab refinement for a later
  task.

## Out of Scope

- Backend API contract changes.
- Full graph editing rewrite.
- User authentication.
- Persistent database beyond current local run artifacts.
- Full paper export implementation.

## Acceptance Criteria

- [x] Top menu contains Home, Analysis, KG Studio, Experiments.
- [x] Analysis has Live and History subnavigation.
- [x] Upload completion opens the generated analysis detail route.
- [x] History entries open `/analysis/:runId`.
- [x] Detail route loads a run by URL and displays a timeline/stepper.
- [x] Timeline stages include input, model/evidence, normalized evidence,
  linking, correction, paths, and review/provenance.
- [x] No backend reasoning logic is duplicated in the UI.
- [x] Typecheck, frontend build, dashboard smoke, and relevant Python gates pass.

## Implementation Notes

- Added `react-router-dom` and module routes for Home, Analysis, KG Studio, and
  Experiments.
- Reframed Analysis as Live, History, and Detail views.
- Replaced the previous all-at-once detail grid with a stepper-driven
  investigation timeline.
- Kept upload, KG Studio, review feedback, and API contracts unchanged.
