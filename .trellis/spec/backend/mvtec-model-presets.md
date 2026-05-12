# MVTec Model Presets

Web image uploads use explicit MVTec model presets so model selection stays
traceable across UI, API, producer records, and run artifacts.

## Scenario: MVTec Image Model Presets

### 1. Scope / Trigger

- Trigger: implementing or changing MVTec raw-image upload model selection,
  model checkpoint resolution, or image upload API fields.
- Applies to `src/kgtracevis/producers/`, `src/kgtracevis/service/`, and the web
  client when it calls the image upload route.
- Reason: model outputs are producer evidence, not semantic defect labels or
  verified RCA.

### 2. Signatures

Backend producer helpers:

```python
def list_mvtec_model_presets() -> list[dict[str, Any]]:
    ...

def resolve_mvtec_model_selection(model_preset: str | None = None) -> MVTecModelSelection:
    ...
```

Service upload contract:

```text
POST /api/runs/upload
form fields:
  file: UploadFile
  mode: evidence | records | image
  dataset?: mvtec | tep | wafer
  object_name?: string
  defect_type?: string
  model_preset?: auto | efficientad | patchcore | stfpm
  top_k: int >= 1
```

Preset discovery:

```text
GET /api/runs/mvtec-model-presets
```

### 3. Contracts

- `model_preset="auto"` chooses the first available preset in this priority:
  `efficientad`, `patchcore`, `stfpm`.
- `stfpm` resolves from `KGTRACEVIS_MVTEC_STFPM_CHECKPOINT` or the checked-in
  OpenVINO checkpoint path.
- `patchcore` resolves from `KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT` or
  `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt`.
  The configured path may be either an Anomalib-compatible checkpoint file or
  an official Amazon PatchCore artifact directory containing
  `patchcore_params.pkl` and `nnscorer_search_index.faiss`.
  It may also be an official Amazon PatchCore object root containing one or
  more object-specific directories named `mvtec_<object>`, such as
  `mvtec_bottle` or `mvtec_metal_nut`; service image uploads must resolve this
  root by the uploaded `object_name` before instantiating the predictor.
- `efficientad` resolves from `KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT` or
  `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_efficientad.pt`.
- `.xml` checkpoints use `anomalib-openvino`; `.ckpt` PatchCore Lightning
  checkpoints use `anomalib-engine`; `.pt` and `.pth` checkpoints use
  `anomalib-torch`; official Amazon PatchCore artifact directories use
  `amazon-patchcore`.
- Image upload run summaries and artifacts must record `model_preset`,
  `model_backend`, and `checkpoint_path`.
- `defect_type` remains optional human/source prior. Do not present it as a
  model-inferred semantic defect class.
- Official Amazon PatchCore on macOS may require the runtime environment
  `KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
  VECLIB_MAXIMUM_THREADS=1` when FAISS and PyTorch share OpenMP runtimes.
- Official Amazon PatchCore `score` is an unbounded distance-like value. Keep it
  as raw `score`, clamp producer `confidence` to `[0, 1]`, and do not interpret
  a fixed `threshold=0.5` mask as reliable localization without calibration.
- Official Amazon PatchCore artifacts are object-specific. Full MVTec coverage
  requires one artifact directory per object under a common root. Supported
  object names follow MVTec AD names (`bottle`, `metal_nut`, `toothbrush`, etc.)
  and resolve to directories named `mvtec_<object>`.
- Git LFS pointer-only Amazon PatchCore files do not count as available
  artifacts. Availability checks must require the real `patchcore_params.pkl`
  and `nnscorer_search_index.faiss` contents, not just matching filenames.

### Official Amazon PatchCore Artifact Root Contract

Official Amazon PatchCore artifacts are saved per object. Do not document or
implement them as one global all-MVTec model. A full root should look like:

```text
<patchcore-artifact-root>/
|-- mvtec_bottle/
|   |-- patchcore_params.pkl
|   `-- nnscorer_search_index.faiss
|-- mvtec_capsule/
|   |-- patchcore_params.pkl
|   `-- nnscorer_search_index.faiss
`-- mvtec_metal_nut/
    |-- patchcore_params.pkl
    `-- nnscorer_search_index.faiss
```

The root may also be an ancestor of that `models/` directory, because runtime
resolution searches for supported `mvtec_<object>` artifact directories. The
preferred user-facing path is the direct `models/` root so errors stay short.

Git LFS usage must avoid pointer-only false availability. Recommended clone and
pull patterns:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/amazon-science/patchcore-inspection.git
cd patchcore-inspection
git lfs install --local

# Selected object artifacts.
git lfs pull -I "models/<run-name>/models/mvtec_bottle/**"
git lfs pull -I "models/<run-name>/models/mvtec_metal_nut/**"

# All model artifacts tracked by the repo.
git lfs pull -I "models/**"
```

If `patchcore_params.pkl` or `nnscorer_search_index.faiss` starts with
`version https://git-lfs.github.com/spec/v1`, the file is a pointer and must be
pulled before the object is considered available.

CLI record generation should pass the full object root with
`--object-checkpoint-root` and `--model-backend amazon-patchcore`; the router
resolves the object from each image path. Web/API image upload should allow
`KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT` to point at the same root and then
resolve by uploaded `object_name`.

On macOS, official Amazon PatchCore smoke runs may require:

```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
```

### Official Amazon PatchCore Smoke Baseline

The local DS-MVTec bottle smoke with official
`IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_bottle` artifacts and
pretrained WR50 verified engineering stability, not paper-grade detection
quality:

```text
source: /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec/bottle/image
run: runs/amazon_patchcore_stability_real_wr50_all_bottle
attempted: 83
producer_ok: 83
producer_failed: 0
adapter_ok: true
adapter_case_count: 83
mean_elapsed_per_image: ~0.276s on local CPU with OpenMP threads pinned to 1
score_range: 1.87 - 10.60
good_score_mean: 2.30
broken_small_score_mean: 7.72
broken_large_score_mean: 7.90
contamination_score_mean: 6.39
mask_area_ratio_range: 0.943 - 0.982
```

Interpretation:

- The backend, producer record writer, Evidence adapter, and KGTracePipeline are
  stable for this object-level smoke.
- Scores separate `good` from most defect samples well enough for anomaly
  intensity evidence.
- The generated masks cover most of the image for both `good` and defect
  samples under the current fixed threshold, so mask-derived
  location/morphology should be treated as low-trust until anomaly-map
  normalization or threshold calibration is added.
- The selected official artifact root has since been downloaded for all 15
  MVTec objects and verified through full-class smoke on CPU.
- Supervised quick calibration is available through
  `scripts/calibrate_mvtec_patchcore_thresholds.py`, producing
  `configs/mvtec_patchcore_thresholds.json/csv`. Passing
  `--threshold-config configs/mvtec_patchcore_thresholds.json` to
  `scripts/build_dataset_records.py` applies per-object `score_threshold` and
  `map_threshold` values while preserving raw scores and threshold provenance.
- The calibrated full-class smoke produced 30 records, 15/15 sampled defect
  images predicted anomalous, 14/15 sampled good images predicted normal, and
  mean mask area ratio around 0.058. This is a pragmatic evidence-generation
  calibration, not an unsupervised MVTec benchmark.
- `scripts/run_mvtec_calibrated_pipeline.py` is the one-command path for paper
  and demo artifacts. It builds a bounded DS-MVTec input subset, applies the
  calibrated Amazon PatchCore producer path, writes records, and runs the
  Evidence adapter plus `KGTracePipeline` summary/table outputs.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Unknown `model_preset` | raise `ValueError` naming supported presets |
| Explicit preset has no checkpoint | return API 400 with the preset/env/default path |
| `auto` has no available checkpoints | return API 400 listing configured checkpoint options |
| Checkpoint exists but Anomalib cannot load it | fail at producer boundary; do not emit fake records |
| Amazon PatchCore object root lacks uploaded object | return API 400/FileNotFound with expected `mvtec_<object>` path and available objects |
| Amazon PatchCore files are Git LFS pointers | treat preset/root/object as unavailable and instruct the user to run `git lfs pull` |
| Raw image omits `defect_type` | emit `anomaly_type="unknown"` unless other source labels exist |

### 5. Good/Base/Bad Cases

Good:

```python
detail = create_run_from_upload(..., mode="image", model_preset="auto")
assert detail.run.model_preset in {"efficientad", "patchcore", "stfpm"}
assert detail.artifacts["checkpoint_path"]
```

Base:

```python
detail = create_run_from_upload(..., mode="image", model_preset="stfpm")
assert detail.run.model_backend == "anomalib-openvino"
```

Bad:

```python
# Do not treat an optional operator prior as model classification.
detail = create_run_from_upload(..., mode="image", defect_type="crack")
assert detail.evidence["anomaly_type"] == "crack"
assert detail.run.model_preset != "crack"
```

### 6. Tests Required

- Preset discovery route includes `auto` and availability metadata.
- Image upload accepts `model_preset` and records `model_preset` plus
  `model_backend` in the run summary/artifacts.
- Missing explicit preset checkpoint returns a 400-level API error.
- Raw image upload without `defect_type` still produces unknown semantic defect
  evidence rather than fake morphology or fake class labels.

### 7. Wrong vs Correct

#### Wrong

```python
# Silent fallback hides model provenance.
try:
    predictor = EfficientAD(...)
except FileNotFoundError:
    predictor = FakePredictor()
```

#### Correct

```python
selection = resolve_mvtec_model_selection(model_preset)
predictor = AnomalibMVTecBackend(
    backend=selection.backend,
    checkpoint=selection.checkpoint_path,
)
```

## Scenario: DS-MVTec Target-Domain PatchCore Runs

### 1. Scope / Trigger

- Trigger: adding or changing scripts/helpers that fit PatchCore on a local
  DS-MVTec object and feed the resulting anomaly evidence into the MVTec record
  producer and KGTracePipeline.
- Applies to `src/kgtracevis/experiments/mvtec_patchcore.py`,
  `scripts/fit_mvtec_patchcore.py`, and `scripts/run_mvtec_patchcore_batch.py`.
- Reason: the reusable experiment path must distinguish model evidence from
  source folder labels, and must preserve enough quality metadata to decide
  whether mask evidence is trustworthy.

### 2. Signatures

Single-object command:

```text
python scripts/fit_mvtec_patchcore.py
  --object-dir PATH
  [--output-root PATH]
  [--name TEXT]
  [--normal-label LABEL]
  [--eval-label LABEL ...]
  [--fit-label LABEL ...]
  [--max-eval-per-label INT>=1]
  [--top-k INT>=1]
  [--device cpu|mps|gpu|auto]
  [--overwrite]
```

Batch command:

```text
python scripts/run_mvtec_patchcore_batch.py
  --dataset-root PATH
  [--output-root PATH]
  [--object NAME ...]
  [--max-objects INT>=1]
  [--max-eval-per-label INT>=1]
  [--top-k INT>=1]
  [--device cpu|mps|gpu|auto]
  [--normal-label LABEL]
  [--overwrite]
```

Reusable helper:

```python
@dataclass(frozen=True)
class PatchCoreObjectRunConfig:
    object_dir: Path
    output_root: Path
    name: str | None = None
    normal_label: str = "good"
    fit_labels: Sequence[str] | None = None
    eval_labels: Sequence[str] | None = None
    max_eval_per_label: int = 1
    top_k: int = 5
    device: str = "cpu"
    overwrite: bool = False

def run_patchcore_object(config: PatchCoreObjectRunConfig) -> dict[str, Any]:
    ...
```

### 3. Contracts

- `--dataset-root` may point either at `DS-MVTec/` or at its parent directory.
- Valid object directories must contain `image/<normal_label>/`.
- If `--object` is omitted, object discovery sorts valid object directories by
  name and skips incomplete non-object entries such as metadata files.
- PatchCore fitting uses `image/<normal_label>` as normal data and selected
  `image/<defect>` directories plus matching `mask/<defect>` directories for
  threshold calibration.
- The generated eval root is a symlinked or copied MVTec-like layout under the
  run directory: `<input_root>/<object>/test/<label>/...` and
  `<input_root>/<object>/ground_truth/<label>/...`.
- Source paths used for symlinks must be resolved before linking so relative
  `object_dir` inputs do not create broken links.
- Object summaries must include: `checkpoint`, `records_path`,
  `adapter_summary`, `adapter_table`, `record_count`, selected fit/eval labels,
  and `sanity`.
- `sanity` must include detection counts for good and defect records, score
  range, predicted mask-area range, and optional mean IoU when `mask_path` and
  `gt_mask_path` are available.
- Batch outputs must include `batch_summary.json` and `batch_summary.csv` with
  one row per object, including status, artifact paths, quality metrics, and
  error text for failures.
- Folder labels remain source annotations. PatchCore outputs only anomaly
  score, anomaly/normal prediction, heatmap, and localization mask evidence.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| `object_dir` does not exist | raise `FileNotFoundError` before fitting |
| `max_eval_per_label < 1` or `top_k < 1` | raise `ValueError` |
| Missing `image/<normal_label>` | raise `FileNotFoundError` |
| Requested object missing under dataset root | raise `FileNotFoundError` during discovery |
| Requested fit/eval label directory missing | raise `FileNotFoundError` |
| PatchCore fit completes without a checkpoint | raise `FileNotFoundError` |
| Existing object summary is valid and `--overwrite` is absent | record `status=skipped_existing` |
| Existing object summary is unreadable/corrupt | record `status=failed`, preserve error text, continue batch |
| One object fails during batch fit/eval | record `status=failed`, preserve error text, continue remaining objects |
| Prediction label text is `abnormal` | treat as anomalous, not normal |

### 5. Good/Base/Bad Cases

Good:

```bash
uv run python scripts/run_mvtec_patchcore_batch.py \
  --dataset-root /path/to/Defect_Spectrum/DS-MVTec \
  --output-root runs/patchcore_defect_spectrum/batch_smoke \
  --object bottle \
  --max-eval-per-label 1 \
  --device cpu \
  --overwrite
```

Base:

```python
summary = run_patchcore_object(
    PatchCoreObjectRunConfig(
        object_dir=Path("DS-MVTec/bottle"),
        output_root=Path("runs/patchcore/bottle"),
        max_eval_per_label=1,
        device="cpu",
        overwrite=True,
    )
)
assert summary["claim_boundary"].startswith("PatchCore outputs")
```

Bad:

```python
# Do not count substring "normal" inside "abnormal" as a normal prediction.
summary = summarize_records([
    {"defect_type": "crack", "detector": {"raw_pred_label": "abnormal"}}
])
assert summary["defect_pred_anomalous_count"] == 1
```

### 6. Tests Required

- Object discovery accepts both `DS-MVTec/` and its parent directory.
- Eval-root construction works for relative `object_dir` inputs by producing
  readable symlink/copy targets.
- Summary aggregation counts good-vs-defect predictions and score/mask ranges.
- IoU aggregation is tested with tiny synthetic mask files.
- Prediction parsing treats `abnormal`/`anomalous` before checking `normal`.
- Batch JSON/CSV writing preserves failed-object rows and error text.
- Do not put Anomalib training in unit tests; real PatchCore fit/eval belongs
  in explicit smoke commands under `runs/`.

### 7. Wrong vs Correct

#### Wrong

```python
# Broken when object_dir is relative and the destination is nested in runs/.
destination.symlink_to(image_path)
```

#### Correct

```python
destination.symlink_to(image_path.resolve())
```

#### Wrong

```python
if "normal" in label.lower():
    return False
if "abnormal" in label.lower():
    return True
```

#### Correct

```python
if any(token in label.lower() for token in ("true", "anomal", "abnormal", "defect")):
    return True
if any(token in label.lower() for token in ("false", "normal", "good")):
    return False
```
