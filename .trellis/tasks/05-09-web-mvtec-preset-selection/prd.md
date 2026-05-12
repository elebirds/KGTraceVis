# brainstorm: web MVTec preset selection

## Goal

Make the web MVTec image-upload flow recognize the PatchCore checkpoint downloaded through the existing Makefile/API model-asset path, so `auto` and explicit `patchcore` selections resolve to the intended model instead of falling back to STFPM.

## What I Already Know

* The user installed PatchCore through the Makefile but the current web run still records the STFPM OpenVINO checkpoint.
* `make download-patchcore` calls `scripts/download_model_assets.py --output-root runs/real_model_pipeline --model mvtec-patchcore`.
* The downloader writes PatchCore to `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt`.
* The MVTec preset resolver currently defaults PatchCore to `data/external/checkpoints/mvtec_patchcore.ckpt`, so the web preset discovery route can miss the Makefile-downloaded asset.
* The React upload UI already calls `/api/runs/mvtec-model-presets` and sends `model_preset` for image uploads.

## Assumptions

* The intended default local asset location for the web workflow is the same `runs/real_model_pipeline/assets/...` path used by Makefile and the API download route.
* Explicit environment variables should continue to override the default path.
* The UI should keep showing model provenance instead of hiding fallback behavior.

## Open Questions

* None blocking. The repository code already exposes the desired Makefile and web API contracts.

## Requirements

* PatchCore preset discovery must mark the Makefile-downloaded checkpoint as available.
* Image upload `auto` should resolve to PatchCore when EfficientAD is absent and PatchCore exists in the Makefile/API asset directory.
* Explicit `model_preset=patchcore` should use the same downloaded checkpoint without requiring a manual environment variable.
* Web-facing text should make the local asset path behavior understandable.

## Acceptance Criteria

* [x] `/api/runs/mvtec-model-presets` reports PatchCore as available when `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt` exists.
* [x] The web upload preset list can expose PatchCore availability without manual env setup.
* [x] Tests cover the Makefile-downloaded PatchCore path.
* [x] Existing STFPM fallback behavior remains available when no higher-priority preset exists.

## Completion Notes

* PatchCore now defaults to
  `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt`.
* `.ckpt` PatchCore presets resolve to the `anomalib-engine` backend.
* The preset API exposes `download_asset`, and the React upload panel can
  request a trusted default download before image upload.
* Verified through service API tests, focused producer tests, and the broader
  checks reported in the weight-download and PatchCore tasks.

## Definition of Done

* Tests added/updated.
* Relevant docs/spec notes updated for the default checkpoint path.
* Focused quality checks run.

## Out of Scope

* Downloading or validating new third-party model sources beyond the existing trusted asset helper.
* Changing MVTec semantic defect labeling behavior.
* Reworking the full web layout.

## Technical Notes

* Relevant spec: `.trellis/spec/backend/mvtec-model-presets.md`.
* Key files: `src/kgtracevis/producers/mvtec_models.py`, `src/kgtracevis/service/runs.py`, `web/src/App.tsx`, `tests/test_service_api.py`.
