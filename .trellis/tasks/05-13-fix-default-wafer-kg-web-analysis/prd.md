# Fix Default Wafer KG For Web Analysis

## Goal

Ensure the default web Analysis pipeline loads the hardened MVTec and Wafer KG
layers so real WM811K uploads produce credible links and paths.

## Bug Found During Browser Test

Uploading `runs/real_model_pipeline/assets/wm811k/wm811k_records.jsonl` through
the web UI produced:

- anomaly `Loc`
- selected anomaly entity `NearfullDefect`
- selected location/morphology entity `GlueRemovalInsufficient`
- top path `NearfullDefect -> GlueRemovalInsufficient`

This contradicts the intended wafer KG behavior and the existing tests that
prevent Loc from routing through Nearfull.

## Requirements

- Load task-specific MVTec/Wafer KG CSV layers in the default KG.
- Preserve skip-missing behavior for fresh checkouts.
- Add/adjust tests so default graph linking routes WM811K Loc to `LocDefect`.
- Do not weaken claim-boundary wording.

## Acceptance Criteria

- [x] `KnowledgeGraph.from_default_paths()` includes hardened wafer nodes/edges.
- [x] Real WM811K Loc record links to `LocDefect`, `WaferLocalLocation`, and
  `WaferClusteredMorphology`.
- [x] Real WM811K Loc top path does not target `GlueRemovalInsufficient`.
- [x] Web upload retest for WM811K no longer shows Nearfull/GlueRemoval for Loc.
- [x] Unit tests and dashboard smoke pass.

## Completion Notes

- Promoted generated MVTec/Wafer hardened KG rows into tracked scenario KG CSVs.
- Updated default KG loading so web/API/script analysis includes the scenario KG layers.
- Kept candidate KG generation anchored to the base KG so review/export artifacts remain reproducible.
- Retested real browser uploads for:
  - `runs/real_model_pipeline/assets/mvtec/mvtec_records.jsonl`
  - `runs/real_model_pipeline/assets/wm811k/wm811k_records.jsonl`

## Out of Scope

- Full KG Studio redesign.
- Visual wafer map rendering.
- Changing source confidence semantics.
