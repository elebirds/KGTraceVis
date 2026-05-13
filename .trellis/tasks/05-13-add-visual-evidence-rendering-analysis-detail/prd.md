# Add Visual Evidence Rendering To Analysis Detail

## Goal

Make the Analysis detail page useful for real MVTec and WM811K uploads by rendering the visual evidence artifacts behind each case, not only the normalized text and KG paths. MVTec should expose source image, heatmap/mask artifacts when present; wafer should expose a wafer-map preview from producer records when available.

## What I Already Know

- Real web upload works for MVTec and WM811K JSONL records.
- Wafer Loc linking was fixed by loading hardened KG layers by default.
- Current detail page can show path and entity text, but the user cannot inspect image/mask/wafer-map evidence in the UI.
- Raw uploaded records include visual artifact paths such as `source_path`, `mask_path`, `heatmap_path`, `wafer_map_path`, or inline `wafer_map` depending on producer.

## Assumptions

- The API can safely serve local artifact images only when paths exist on disk and are referenced by run evidence/records.
- For wafer maps, a lightweight server-side preview PNG is acceptable for v0.
- This task should not redesign the whole dashboard again; it should improve Analysis detail usefulness.

## Requirements

- Add visual evidence payloads to run detail API responses or expose safe artifact URLs.
- Show MVTec source image and available mask/heatmap artifacts in Analysis detail.
- Show WM811K wafer map preview in Analysis detail when a wafer map path or inline wafer map exists.
- Preserve claim boundaries: visual rendering is observed evidence, not verified RCA.
- Keep core reusable parsing/rendering logic out of UI components where practical.

## Acceptance Criteria

- [x] Real MVTec JSONL upload detail displays source/mask/heatmap artifact panels when files exist or clearly marks missing artifacts.
- [x] Real WM811K JSONL upload detail displays wafer-map visual preview for available map data.
- [x] Browser smoke or automated frontend/API test verifies visual evidence is present for at least one MVTec and one wafer run.
- [x] Existing KG/entity/path behavior remains unchanged.
- [x] Quality gates pass.

## Completion Notes

- Added run-scoped visual evidence preparation under `runs/rootlens_sessions/<run>/artifacts`.
- Added a safe artifact route for browser previews.
- Rendered MVTec source image, mask, and heatmap previews.
- Rendered WM811K wafer-map previews from inline or path-backed map data.
- Verified real web uploads for:
  - `runs/real_model_pipeline/assets/mvtec/mvtec_records.jsonl`
  - `runs/real_model_pipeline/assets/wm811k/wm811k_records.jsonl`

## Definition Of Done

- Tests added or updated for API/UI behavior.
- `uv run --extra dev pytest` passes.
- `uv run --extra dev ruff check .` passes.
- `uv run --extra dev mypy src tests scripts` passes.
- `uv run python scripts/run_examples.py` passes.
- Dashboard smoke passes.

## Out Of Scope

- Full KG Studio graph editing.
- Full image annotation editor.
- Model re-inference or new model training.
- Large raw dataset commits.

## Technical Notes

- Need inspect current web frontend and service API before editing.
