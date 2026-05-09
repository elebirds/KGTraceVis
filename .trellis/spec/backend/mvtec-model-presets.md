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
  `data/external/checkpoints/mvtec_patchcore.pt`.
- `efficientad` resolves from `KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT` or
  `data/external/checkpoints/mvtec_efficientad.pt`.
- `.xml` checkpoints use `anomalib-openvino`; `.pt`, `.pth`, and `.ckpt`
  checkpoints use `anomalib-torch`.
- Image upload run summaries and artifacts must record `model_preset`,
  `model_backend`, and `checkpoint_path`.
- `defect_type` remains optional human/source prior. Do not present it as a
  model-inferred semantic defect class.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Unknown `model_preset` | raise `ValueError` naming supported presets |
| Explicit preset has no checkpoint | return API 400 with the preset/env/default path |
| `auto` has no available checkpoints | return API 400 listing configured checkpoint options |
| Checkpoint exists but Anomalib cannot load it | fail at producer boundary; do not emit fake records |
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
