# Supervised Amazon PatchCore Calibration

## Goal

Add a pragmatic supervised calibration path for official Amazon PatchCore MVTec evidence so paper-deadline runs can produce usable image and mask predictions from calibrated per-object thresholds while preserving raw model scores and clear provenance.

## Requirements

* Add reusable, testable calibration logic under `src/kgtracevis/` that consumes producer JSONL-style records containing scores, anomaly maps, masks, source labels, and ground-truth masks.
* Compute per-object image score thresholds and anomaly-map thresholds from bounded samples of good and defect MVTec images.
* Add a calibration script, `scripts/calibrate_mvtec_patchcore_thresholds.py`, for running official Amazon PatchCore over an MVTec-like root and writing `configs/mvtec_patchcore_thresholds.json` and/or CSV plus a run summary under `runs/`.
* Script arguments must include dataset root, artifact root, max per label, device CPU support, and output paths.
* Defaults should be project-relative or otherwise safe; avoid hard-coded absolute paths except user-supplied CLI values.
* Extend the MVTec Amazon PatchCore producer path so a threshold config can be passed through `scripts/build_dataset_records.py`.
* Applying thresholds must preserve raw score and add provenance metadata: `threshold_source`, `uses_ground_truth`, `calibration_scope` or object, `score_threshold`, and `map_threshold`.
* Use the score threshold for anomaly confidence and image-level anomalous/normal decision; use the map threshold for predicted mask generation.
* Add tests for threshold config loading/applying and calibration helper behavior.
* Do not commit changes.

## Acceptance Criteria

* [x] Calibration helpers are small, reusable, and covered by focused tests.
* [x] Calibration script can be run with bounded samples and writes threshold artifacts plus summary output.
* [x] `build_dataset_records.py` accepts a threshold config for `mvtec` + `amazon-patchcore` and applies it through reusable producer code.
* [x] Producer records preserve raw scores and include threshold provenance metadata.
* [x] Focused tests pass.

## Definition of Done

* Tests added/updated for core threshold behavior.
* Focused test command run and reported.
* Full expensive calibration command left ready if not run.
* Files changed and residual risks summarized.

## Out of Scope

* Strict unsupervised MVTec benchmark evaluation.
* Training new models.
* Claiming MVTec root-cause labels or verified industrial causes.
* Running full calibration over all artifacts if it is too expensive for the current session.

## Technical Notes

* Relevant existing paths are expected around `src/kgtracevis/producers/`, `scripts/build_dataset_records.py`, `scripts/run_real_model_pipeline.py`, and producer tests.
* Project constraints from `AGENTS.md` apply: reusable logic belongs under `src/kgtracevis/`, scripts are clients, paths should be configurable, and generated outputs belong under `runs/`, `outputs/`, or `artifacts/`.

## Implementation Notes

Implemented:

* `src/kgtracevis/producers/mvtec_calibration.py`
* `scripts/calibrate_mvtec_patchcore_thresholds.py`
* `scripts/build_dataset_records.py --threshold-config`
* producer application of calibrated `score_threshold` / `map_threshold`
* focused tests in `tests/test_record_producers.py`

Local quick calibration command completed with:

```text
record_count=86
object_count=15
output_config=configs/mvtec_patchcore_thresholds.json
output_csv=configs/mvtec_patchcore_thresholds.csv
summary=runs/mvtec_patchcore_quick_calibration/calibration_summary.json
```

Calibrated full-class smoke completed with:

```text
records=30
adapter_case_count=30
defect_anomalous=15/15
good_normal=14/15
good_anomalous=1/15
mask_area_mean≈0.058
summary=runs/amazon_patchcore_full_class_smoke_calibrated/calibrated_full_class_smoke_summary.json
```

Residual risk: `pill/good` remains high-score/anomalous under the quick
supervised thresholds, so this is usable evidence calibration rather than a
paper-grade detector evaluation.
