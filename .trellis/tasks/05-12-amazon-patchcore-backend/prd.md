# Amazon PatchCore Backend Adaptation

## Goal

Add a KGTraceVis MVTec producer backend that can consume official Amazon
`patchcore-inspection` PatchCore artifacts and emit the existing normalized
MVTec producer prediction shape.

## Motivation

The current `patchcore` preset path assumes Anomalib-style exported checkpoints.
Amazon's official PatchCore repository publishes/loads artifacts as a directory
containing `patchcore_params.pkl` and `nnscorer_search_index.faiss`; that format
is not compatible with Anomalib `.ckpt` loading. KGTraceVis needs a traceable
adapter boundary that can use official artifacts without pretending they are
Anomalib models.

## MVP Scope

- Add a `amazon-patchcore` MVTec backend under `src/kgtracevis/producers/`.
- Accept a local official PatchCore artifact directory via `--checkpoint`.
- Validate required official files before runtime inference.
- Load the official `patchcore-inspection` package dynamically when the backend
  is selected.
- Normalize official PatchCore outputs into `MVTecPrediction`:
  - `score`
  - `confidence`
  - optional `label`
  - `anomaly_map`
  - metadata with backend, checkpoint, device, and model format
- Wire the backend into `scripts/build_dataset_records.py`.
- Add unit tests using injected model objects so CI does not require FAISS,
  torch downloads, or the official repository.

## Explicit Non-Goals

- Do not add semantic defect type inference.
- Do not emit root causes or KG paths from the producer.
- Do not silently fall back to fake records when the official package/artifact is
  missing.
- Do not automatically download large Git LFS assets in this MVP.

## Acceptance Criteria

- `build_mvtec_predictor(model_backend="amazon-patchcore", checkpoint=...)`
  returns the new backend.
- Missing official artifact files fail with actionable errors.
- Injected official-like predictions normalize to the same record path consumed
  by `build_mvtec_records`.
- Existing producer tests still pass.
- The backend metadata makes the model provenance and format explicit.
