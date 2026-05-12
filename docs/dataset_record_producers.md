# Dataset Record Producers

Producer modules live under `src/kgtracevis/producers/`. They are the optional
model-aware layer before the existing Evidence adapters:

```text
local raw/subset data -> producer inference -> normalized records -> Evidence adapters
```

The producer contract is intentionally narrow. Producers emit plain record
dictionaries or JSONL files. They do not create `Evidence`, do not import
`KGTracePipeline`, and filter root-cause or path-ranking keys such as
`root_cause`, `top_k_paths`, and `kg_analysis`.

## Local Data

Place raw datasets and checkpoints under ignored paths:

- MVTec or DS-MVTec-like folders: `data/external/mvtec/`
- WM811K tables: `data/external/wafer/`
- generated producer records: `data/processed/records/`
- generated masks, heatmaps, wafer maps, or saliency arrays:
  `data/processed/records/<output-stem>/`

Do not commit raw datasets, model weights, generated records, or generated model
outputs.

## MVTec

The first MVTec producer scans a standard tiny MVTec-like tree such as:

```text
data/external/mvtec/
└── bottle/
    ├── test/
    │   ├── scratch/
    │   │   └── 000.png
    │   └── good/
    │       └── 001.png
    └── ground_truth/
        └── scratch/
            └── 000_mask.png
```

It calls a predictor once per selected image and emits records with
`dataset="mvtec"`, object/category, detector score, confidence, generated
heatmap or mask paths when arrays are produced, mask geometry stats, source path
metadata, and model metadata. If the source tree has a native defect folder such
as `crack` or `scratch`, that value is recorded as source label provenance, not
as a model-inferred defect class.

MVTec/Anomalib producer scope is anomaly detection and localization:

- anomaly score or confidence,
- normal/anomalous prediction label when the backend provides it,
- anomaly heatmap and predicted mask,
- deterministic geometry derived from the mask.

It does not directly solve semantic defect-type classification. For user uploads
or flat image inputs without a reviewed native label, records should use an
unknown or generic visual anomaly type and preserve any operator-supplied label
as optional human prior metadata. A later defect-type classifier may be added as
a separate producer that emits reviewable semantic candidates, but it should not
be conflated with the anomaly detector.

Real MVTec command:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_subset.jsonl \
  --model-backend anomalib-openvino \
  --checkpoint data/external/checkpoints/mvtec_openvino.xml \
  --max-per-label 10 \
  --overwrite
```

Real exported Anomalib inference is selected with `--model-backend
anomalib-torch` or `--model-backend anomalib-openvino`. The producer imports
Anomalib only at runtime for those backend names, so the deterministic test
suite does not require Anomalib or a checkpoint.

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_patchcore_subset.jsonl \
  --model-backend anomalib-torch \
  --checkpoint data/external/checkpoints/mvtec_patchcore.pt \
  --device cpu \
  --threshold 0.5 \
  --max-per-label 10 \
  --overwrite
```

## WM811K

The first WM811K producer reads a pandas-readable table (`.csv`, `.json`,
`.jsonl`, `.pkl`, or `.parquet`) with common fields such as `waferMap`,
`failureType`, `lotName`, and `waferIndex`. It calls a classifier per wafer map
and emits records with `dataset="wafer"` and `adapter="wm811k"`, predicted
pattern, classification confidence, descriptor stats, optional inline tiny wafer
map or generated map path, native label provenance when present, and model
metadata.

Real WM811K command:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input data/external/wafer/LSWMD.pkl \
  --output-jsonl data/processed/records/wm811k_subset.jsonl \
  --model-backend torch-resnet34 \
  --checkpoint data/external/checkpoints/wm811k_resnet34.pt \
  --max-per-label 50 \
  --overwrite
```

Local sklearn-compatible classifiers are selected with `--model-backend
sklearn`. The checkpoint is loaded with joblib first, then pickle as a fallback.
Both formats can execute code while loading; only use trusted local model files
under ignored paths such as `data/external/checkpoints/`.

The classifier receives each wafer map flattened into one feature row. If the
model exposes `predict_proba`, the probability for the predicted class becomes
`classification_confidence`; exposed `classes_` are preserved in model metadata.

```bash
uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input data/external/wafer/LSWMD.pkl \
  --output-jsonl data/processed/records/wm811k_sklearn_subset.jsonl \
  --model-backend sklearn \
  --checkpoint data/external/checkpoints/wm811k_classifier.joblib \
  --max-per-label 50 \
  --overwrite
```

End-to-end pipeline command:

```bash
uv run python scripts/run_real_model_pipeline.py \
  --output-root runs/real_model_pipeline \
  --overwrite
```

MVTec and WM811K public records contain observations, native labels, and model
outputs only. Candidate root-cause paths are generated later by
`KGTracePipeline` and remain plausible runtime explanations, not dataset-native
verified causes.

The user-facing commands use real inputs and real checkpoints. Deterministic
fake predictors remain only in the test suite.
