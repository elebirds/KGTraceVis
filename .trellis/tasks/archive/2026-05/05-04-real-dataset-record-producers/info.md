# Real Dataset Record Producers: Implementation Notes

Date: 2026-05-04

## Implemented Scope

- Added `src/kgtracevis/producers/` as the model-dependent layer in front of
  the existing Evidence adapters.
- Added shared producer utilities for JSONL writing, deterministic subset
  selection, predictor protocols, model metadata, checkpoint hashing, and
  recursive forbidden RCA/path-output filtering.
- Added MVTec producer:
  - scans MVTec-like image folders,
  - calls a predictor per image,
  - writes generated heatmap/mask JSON assets when arrays are returned,
  - emits `dataset="mvtec"` records with model score/confidence and provenance.
- Added WM811K producer:
  - reads pandas-readable wafer-map tables,
  - calls a classifier per wafer map,
  - computes descriptor stats,
  - emits `dataset="wafer"`, `adapter="wm811k"` records with predicted pattern,
    confidence, native-label provenance, and model metadata.
- Added real local backend wrappers:
  - MVTec `anomalib-torch` / `anomalib-openvino` optional runtime backends,
  - WM811K `sklearn` trusted local joblib/pickle checkpoint backend.
- Added `scripts/build_dataset_records.py` as a thin CLI for fake and local
  model backends.
- Added `configs/dataset_records.example.yaml` and docs for local data,
  checkpoint, and producer-to-adapter commands.

## Verification

- `uv run --extra dev pytest -q`: 110 passed.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra dev mypy src tests scripts`: passed.
- `uv run python scripts/run_examples.py`: validated 4 examples.
- Smoke: MVTec fake backend generated records and ran through
  `scripts/run_adapter_pipeline.py`.
- Smoke: WM811K sklearn `DecisionTreeClassifier` joblib checkpoint generated
  records and ran through `scripts/run_adapter_pipeline.py`.

## Remaining Limitations

- Real Anomalib exported checkpoints were not available in this environment, so
  Anomalib backend tests use an injected fake inferencer while preserving the
  runtime API boundary.
- WM811K sklearn backend assumes the flattened wafer-map feature width matches
  the saved classifier.
- Local joblib/pickle checkpoints are trusted-local only.
