# WM811K Model Presets

WM811K model integrations are producer-level defect-pattern classifiers. They
produce observed wafer-map evidence for the shared `wafer` Evidence schema; they
do not produce verified root-cause labels.

## Scenario: Public WM811K ResNet Evidence Producer

### 1. Scope / Trigger

- Trigger: changing WM811K model downloads, CLI producer arguments, classifier
  backend metadata, real-model pipeline wiring, or WM811K producer docs/tests.
- Applies to `src/kgtracevis/producers/`, `scripts/build_dataset_records.py`,
  `scripts/download_model_assets.py`, `scripts/run_real_model_pipeline.py`, and
  WM811K producer/adaptor tests.
- Reason: WM811K model outputs feed Evidence and downstream RCA modules, so the
  producer must preserve provenance while avoiding unsupported causal claims.

### 2. Signatures

Model asset download:

```bash
uv run python scripts/download_model_assets.py --model wm811k-resnet --include-wm811k-data
```

Producer record build:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input runs/real_model_pipeline/assets/wm811k/input_tables/test.pkl \
  --output-jsonl data/processed/records/wm811k_subset.jsonl \
  --model-backend torch-resnet34 \
  --checkpoint runs/real_model_pipeline/assets/wm811k/checkpoints/best_radai_resnet.pt \
  --model-source-repo radai-agent/radai-wm811k-defect-detection \
  --model-source-file best_radai_resnet.pt \
  --overwrite
```

Backend construction:

```python
TorchWM811KBackend(
    checkpoint=checkpoint,
    device="cpu",
    model_source="radai-agent/radai-wm811k-defect-detection",
    model_file="best_radai_resnet.pt",
)
```

### 3. Contracts

- Default public asset:
  - repo: `radai-agent/radai-wm811k-defect-detection`
  - file: `best_radai_resnet.pt`
  - backend: `torch-resnet34`
  - task: `defect_pattern_classification`
- Default public input table:
  - repo: `lslattery/wafer-defect-detection`
  - file: `test.pkl`
  - repo_type: `dataset`
  - local path: `runs/real_model_pipeline/assets/wm811k/input_tables/test.pkl`
- Supported public defect classes:
  `Center`, `Donut`, `Edge-Loc`, `Edge-Ring`, `Loc`, `Random`, `Scratch`,
  `Near-full`.
- The public ResNet is a defect-pattern classifier over labeled WM811K defect
  classes. It must not be described as a normal-wafer detector.
- Producer classifier metadata should preserve:
  - `source_backend`
  - `checkpoint`
  - `device` when applicable
  - `classes`
  - `task="defect_pattern_classification"`
  - `produces_root_cause=False`
  - optional `model_source`
  - optional `model_file`
- `build_wm811k_records` must keep source-table provenance:
  `source_table`, `source_row_index`, `wafer_id`, `native_failure_pattern`, and
  `annotation_type`.
- WM811K records must use `dataset="wafer"`, `adapter="wm811k"`, and
  `source_dataset="wm811k"` so the batch adapter dispatches to
  `evidence_from_wm811k_record`.
- Producer records must not include `root_cause`, `root_causes`,
  `candidate_root_cause`, `candidate_root_causes`, `ranked_causes`,
  `top_k_paths`, or `kg_analysis`.
- WM811K input-table download summaries must report source repo, filename,
  local input path, repo type, and the defect-pattern evidence claim boundary.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| `torch-resnet34` checkpoint is missing | raise `FileNotFoundError` at backend load |
| torch/torchvision is unavailable | raise an import error naming the `torch-resnet34` requirement |
| model output shape is not `[batch, classes]` | raise `ValueError` |
| row has `None`/normal/unlabeled native label and `include_unlabeled=False` | skip the row before inference output is written |
| source repo/file is not passed | still produce records, but omit `model_source`/`model_file` metadata |
| producer or nested output includes reasoning keys | recursively filter them before JSONL writing |

### 5. Good/Base/Bad Cases

Good:

```python
prediction = TorchWM811KBackend(
    checkpoint=checkpoint,
    device="cpu",
    model_source="radai-agent/radai-wm811k-defect-detection",
    model_file="best_radai_resnet.pt",
).predict(wafer_map)
assert prediction["metadata"]["task"] == "defect_pattern_classification"
assert prediction["metadata"]["produces_root_cause"] is False
```

Base:

```python
record = build_wm811k_records(
    input_path,
    classifier,
    model_backend="torch-resnet34",
    checkpoint=checkpoint,
)[0]
assert record["dataset"] == "wafer"
assert record["adapter"] == "wm811k"
assert record["classifier"]["backend"] == "torch-resnet34"
```

Bad:

```python
record = {
    "dataset": "wafer",
    "adapter": "wm811k",
    "failure_pattern": "Edge-Ring",
    "root_cause": "UnsupportedProcessCause",
}
written = filter_forbidden_outputs(record)
assert "root_cause" not in written
```

### 6. Tests Required

- Asset tests:
  - `download_wm811k_resnet` reports repo, filename, backend, class list, task,
    and `produces_root_cause=False`.
  - `download_wm811k_input_table` reports source repo, filename, repo_type,
    local input path, and the observed-evidence claim boundary without network
    access in tests.
  - selected model asset routing accepts `wm811k-resnet` and rejects unknown
    assets.
- Backend tests:
  - synthetic local torch checkpoint loads without network access.
  - prediction metadata includes class list, source backend, optional source
    repo/file, task, and root-cause boundary.
- Producer/adaptor tests:
  - records convert to schema-valid Evidence with `dataset="wafer"` and
    `adapter.name="wm811k"`.
  - classifier metadata and source row provenance survive in record/raw evidence
    extras.
  - root-cause/path-ranking keys are filtered recursively.
- Run at minimum after WM811K model integration changes:

```bash
uv run --extra dev pytest tests/test_model_assets.py tests/test_record_producers.py tests/test_adapters.py
uv run --extra dev pytest
uv run python scripts/run_examples.py
```

### 7. Wrong vs Correct

#### Wrong

```python
record["root_cause"] = "ProcessDrift"
record["classifier"]["produces_root_cause"] = True
```

The classifier predicted a wafer-map defect pattern, not an industrial root
cause. RCA candidates are generated later by KGTracePipeline from evidence plus
source-constrained KG edges.

#### Correct

```python
record["failure_pattern"] = "Edge-Ring"
record["classifier"]["task"] = "defect_pattern_classification"
record["classifier"]["produces_root_cause"] = False
```

The Evidence adapter exposes this as observed wafer evidence, and the RCA module
may later rank candidate paths with explicit source edges.
