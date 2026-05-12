# brainstorm: real dataset record producers

## Goal

Implement a reproducible producer-output record layer for real MVTec/DS-MVTec
and WM811K dataset subsets. Unlike the completed adapter layer, this producer
layer is allowed to run models over each sample image/wafer map, save the model
outputs, emit normalized JSONL records, and then reuse the existing Evidence
adapters and adapter pipeline.

Target flow:

```text
local raw/subset dataset
-> model-dependent producer inference
-> deterministic post-processing / provenance capture
-> producer-output JSONL records
-> existing Evidence adapters
-> KGTracePipeline
-> adapter pipeline tables
-> paper-facing manifest
```

## What I Already Know

- The adapter-first milestone is complete and committed in `6c2f7ae`.
- Existing checked-in record fixtures live under `data/examples/records/`.
- Existing Evidence adapters already consume normalized MVTec and WM811K
  records.
- Existing batch loading supports `.json`, `.jsonl`, and `.csv` record files.
- Existing commands can run generated records end to end:
  - `scripts/generate_evidence.py`
  - `scripts/run_adapter_pipeline.py`
  - `scripts/run_experiment_suite.py`
  - `scripts/build_paper_tables.py`
- Large raw datasets must stay under ignored paths such as `data/external/`,
  `data/interim/`, or `data/processed/`.
- `configs/paths.yaml` already defines `external_data_dir`,
  `processed_data_dir`, and other root paths.
- MVTec and WM811K path outputs must remain candidate/plausible explanations,
  not verified RCA.

## Assumptions

- The user can provide or place local dataset files and model checkpoints under
  ignored paths.
- The next producer milestone should run inference, not just mirror native
  labels into records.
- MVTec producer should support an anomaly detector such as PatchCore or
  EfficientAD, producing image-level score plus anomaly map/mask outputs.
- WM811K producer should support a wafer-map classifier or precomputed
  prediction table, producing pattern label, confidence, and optional saliency
  or attention outputs.
- The producer layer emits records, not `Evidence`, and must not emit root-cause
  answers or runtime path-ranking outputs.

## Requirements

- Add model-aware record producers for:
  - MVTec/DS-MVTec image folder subsets, with per-image inference.
  - WM811K wafer-map table/array subsets, with per-wafer inference or
    precomputed classifier outputs.
- Producers must output normalized record JSONL compatible with existing
  adapters:
  - MVTec records use `dataset="mvtec"`.
  - WM811K records use `dataset="wafer"` and `adapter="wm811k"`.
- Producers must support bounded subset selection:
  - max cases overall,
  - max cases per class/defect/pattern,
  - optional category/object filter,
  - fixed random seed or deterministic sort.
- Producers must record provenance:
  - source dataset,
  - source file/table path,
  - image/mask/wafer-map path or row id,
  - annotation type,
  - generated-at/config metadata where useful.
- Producers must convert model outputs and deterministic post-processing into
  observed evidence records:
  - MVTec: category/object, predicted anomaly score/confidence, anomaly map or
    generated mask path, mask-derived stats, optional dataset defect label and
    caption metadata.
  - WM811K: wafer id, predicted failure pattern, classification confidence,
    wafer map path or compact map stats, descriptor stats, optional saliency or
    attention path, and native label when available for evaluation.
- Producers must not introduce new top-level directories or commit raw data.
- Scripts must be thin clients; reusable producer logic must live under
  `src/kgtracevis/`.

## Candidate Design

Recommended package shape:

```text
src/kgtracevis/producers/
├── __init__.py
├── common.py
├── mvtec_records.py
└── wm811k_records.py

scripts/build_dataset_records.py
configs/dataset_records.example.yaml
tests/test_record_producers.py
```

Recommended command shape:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_subset.jsonl \
  --max-per-label 10 \
  --overwrite

uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input data/external/wm811k/LSWMD.pkl \
  --output-jsonl data/processed/records/wm811k_subset.jsonl \
  --max-per-label 50 \
  --overwrite
```

Then run:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/processed/records/mvtec_subset.jsonl \
  --dataset mvtec \
  --output-dir outputs/adapter_pipeline_real_subset/mvtec \
  --overwrite

uv run python scripts/run_adapter_pipeline.py \
  --input data/processed/records/wm811k_subset.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_real_subset/wm811k \
  --overwrite
```

## Dataset-Specific Plan

### MVTec / DS-MVTec Producer

Inputs to support first:

- Standard MVTec-like folder root with categories and defect folders.
- Optional ground-truth mask folder if present.
- A configured anomaly detector checkpoint or inference backend.
- Optional DS-MVTec-style caption or richer metadata later.

Record fields:

- `dataset="mvtec"`
- `case_id`
- `object`
- `defect_type` from dataset label when available, or predicted/candidate defect
  type from a future semantic component
- `image_path`
- `mask_path` from generated model mask or dataset ground-truth mask when used
  for evaluation
- `heatmap_path` or `anomaly_map_path` when generated
- `mask_stats` from generated mask/anomaly map thresholding
- `confidence` from model `pred_score` or calibrated score
- `annotation_type="native_ground_truth"` for defect labels, while RCA remains
  absent
- model metadata such as `producer.name`, checkpoint path/hash, threshold, and
  inference timestamp
- `source_dataset`, `source_split`, and source path metadata in extra fields

MVP behavior:

- Run inference over selected test images.
- Skip `good` samples by default unless `--include-good` is requested.
- Save generated anomaly maps/masks under ignored processed/interim paths.
- If the real backend is unavailable in tests, use a fake predictor interface so
  producer tests still exercise the model-output contract.

### WM811K Producer

Inputs to support first:

- Pickle/CSV/parquet table where rows contain wafer map and failure type.
- Common fields such as `waferMap`, `failureType`, `lotName`, `waferIndex`.
- A configured classifier checkpoint or precomputed prediction table.
- A fallback column mapping option for local variants.

Record fields:

- `dataset="wafer"`
- `adapter="wm811k"`
- `case_id`
- `wafer_id`
- `failure_pattern` from model prediction; keep native label separately when
  available for evaluation
- `wafer_map` only for tiny subsets when size is safe, otherwise
  `wafer_map_path`
- `defect_density`
- `descriptor_stats`
- `classification_confidence` from model prediction
- `native_failure_pattern` when available
- `model_name`, checkpoint path/hash, and inference metadata
- `annotation_type="native_ground_truth"` for public pattern labels

MVP behavior:

- Exclude unlabeled/none patterns by default.
- Support class-balanced sampling with `--max-per-label`.
- Persist large wafer maps under ignored processed/interim paths if needed.
- Reuse deterministic descriptor helpers from `kgtracevis.mask.wafer_map_features`.
- Use a predictor protocol so tests can run with a deterministic fake classifier.

## Implementation Options

### Option A: Native-Label Producer Only

Only convert local dataset labels/files into records without running inference.

Trade-off: this is mostly what the completed adapter/fixture milestone already
proved. It does not demonstrate real producer/model integration.

### Option B: Model-Aware Producer With Fake-Test Backend

Define predictor interfaces and implement producers that consume model outputs.
Tests use deterministic fake predictors; real local runs use configured
checkpoints/backends.

Trade-off: requires more CLI/config design, but it directly validates the next
paper-relevant layer.

### Option C: Full Training/Evaluation Stack

Train or fine-tune detectors/classifiers, manage checkpoints, and benchmark
detector performance.

Trade-off: too large for the next step and risks turning KGTraceVis into an
anomaly detection paper.

## Recommended MVP

Use Option B:

- Implement model-aware producer interfaces and per-sample inference loops.
- Use fake predictors in tests to avoid checkpoint dependence.
- Add one CLI with direct flags and an example YAML documenting local paths,
  checkpoints, thresholds, subset parameters, and output paths.
- Defer training and detector-performance benchmarking.

This targets the missing layer: real model outputs becoming normalized records.

## Acceptance Criteria

- [x] A task-local or docs plan states the model-dependent producer contract,
      local dataset assumptions, checkpoint assumptions, and fallback test
      strategy.
- [x] MVTec producer can run a predictor over a tiny synthetic MVTec-like test
      fixture and emit score/map/mask-derived records.
- [x] WM811K producer can run a classifier/predictor over a tiny synthetic table
      or pickle fixture and emit predicted pattern/confidence records.
- [x] Generated records validate through existing `evidence_from_records`.
- [x] Generated records run through `run_adapter_pipeline` in tests or smoke
      checks.
- [x] Producers support deterministic subset limits and fixed ordering/seed.
- [x] Tests do not require real checkpoints because predictor interfaces can be
      faked.
- [x] Producers do not emit root-cause/path-ranking fields.
- [x] Raw datasets and generated processed records remain ignored by Git.

## Definition of Done

- Tests added or updated for producer parsing, subset selection, and adapter
  compatibility.
- `uv run --extra dev pytest` passes.
- `uv run --extra dev ruff check .` passes.
- `uv run --extra dev mypy src tests scripts` passes.
- `uv run python scripts/run_examples.py` passes.
- Documentation explains where to place local raw datasets and how to run the
  producer -> adapter pipeline loop.

## Out of Scope

- Training or benchmarking anomaly detectors.
- Downloading raw datasets automatically.
- Committing raw MVTec or WM811K data.
- Adding verified RCA labels for MVTec or public WM811K.
- TEP producer implementation in this task.
- Large manual KG or reference expansion.
- Frontend or Streamlit changes.

## Open Questions

- Which local MVTec inference backend should be first: Anomalib PatchCore,
  Anomalib EfficientAD, or a simpler local checkpoint wrapper?
- Which local WM811K inference backend should be first: an existing classifier
  checkpoint, a precomputed prediction table, or a small sklearn/PyTorch
  wrapper around wafer maps?

## Technical Notes

- Relevant existing files inspected:
  - `docs/adapter_contracts.md`
  - `docs/paper_experiment_protocol.md`
  - `src/kgtracevis/adapters/batch.py`
  - `scripts/generate_evidence.py`
  - `configs/paths.yaml`
  - `.trellis/spec/backend/adapter-guidelines.md`
- Existing dependencies include `numpy` and `pandas`, so CSV/pickle/parquet-like
  table handling can stay inside current dependency policy, though parquet may
  require optional engine availability.
- Reusable producer logic should live under `src/kgtracevis/producers/`.
- Scripts should only parse arguments, call producer functions, and write JSONL
  records.
