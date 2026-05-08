# Adapter Guidelines

Dataset ingestion uses a two-layer contract: optional model-dependent producers
write normalized records, and model-independent Evidence adapters convert those
records into validated `Evidence`.

## Scenario: Two-Layer Dataset Ingestion

### 1. Scope / Trigger

- Trigger: implementing or changing dataset ingestion, producer-output records,
  Evidence adapters, adapter fixtures, or adapter-to-pipeline scripts.
- Applies to MVTec/DS-MVTec, WM811K/wafer, TEP, and future datasets.
- Reason: producer/model work is higher risk and may require human setup; the
  Evidence adapter layer must remain deterministic, testable, and runnable by
  agents without model checkpoints.

### 2. Signatures

Evidence adapter signatures:

```python
def evidence_from_mvtec_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    ...

def evidence_from_wm811k_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    ...
```

Batch conversion signature:

```python
def evidence_from_records(
    records: Sequence[Mapping[str, Any]],
    *,
    dataset: DatasetName | None = None,
) -> list[Evidence]:
    ...
```

Producer-output record files:

```text
data/examples/records/*.jsonl
```

### 3. Contracts

Producer layer:

- May run models, detectors, classifiers, or saliency methods.
- Produces normalized record dictionaries.
- Must not produce `Evidence` directly unless it calls the Evidence adapter.
- Must not be required for the deterministic adapter test suite.
- User-facing producer commands should use real backends and real input files;
  deterministic fake predictors belong in tests and fixture helpers only.

Evidence adapter layer:

- Consumes normalized records, labels, mask stats, wafer-map descriptors, and
  deterministic feature summaries.
- Returns Pydantic `Evidence`.
- Must leave `Evidence.kg_analysis` empty.
- Must set `adapter.produces_root_cause=False`.
- Must not copy root-cause/path-ranking outputs into top-level fields,
  `raw_evidence.extra`, observations, or metadata.

WM811K contract:

- Use `Evidence.dataset == "wafer"`.
- Identify the specific adapter with `adapter.name == "wm811k"` and metadata
  such as `source_dataset="wm811k"` and `schema_dataset="wafer"`.
- Put the canonical wafer pattern in `Evidence.anomaly_type` so existing
  entity-linking and path-ranking source fields work.
- Optional `spatial_pattern` observations are allowed for UI/metrics, but must
  not be the only linkable representation.

MVTec contract:

- Use `Evidence.dataset == "mvtec"` and `source == "image"`.
- Convert object/category, defect/anomaly type, mask geometry, detector scores,
  captions, and heatmap/mask paths into observed evidence.
- MVTec root-cause paths are curated plausible references unless separately
  reviewed; the adapter never emits them.

Forbidden reasoning-output keys include:

```text
root_cause
root_causes
candidate_root_cause
candidate_root_causes
ranked_causes
top_k_paths
kg_analysis
```

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Record contains root-cause keys at top level | Adapter filters them out |
| Record contains root-cause keys nested under `extra` | Adapter recursively filters them out |
| WM811K record has `dataset="wafer"` and `adapter="wm811k"` | Batch dispatcher uses WM811K adapter |
| WM811K record omits explicit location/morphology but has descriptors | Adapter derives deterministic fallback fields |
| MVTec record omits explicit location/morphology but has `mask_stats` | Adapter derives deterministic fallback fields |
| Producer/checkpoint/model dependency is unavailable | Evidence adapter tests still run |
| Adapter would need verified RCA to fill a field | Leave it out; KGTracePipeline computes candidate paths later |

### 5. Good/Base/Bad Cases

Good:

```python
record = {
    "dataset": "wafer",
    "adapter": "wm811k",
    "failure_pattern": "Near-full",
    "defect_density": 0.72,
}
evidence = evidence_from_wm811k_record(record)
assert evidence.dataset == "wafer"
assert evidence.adapter.name == "wm811k"
assert evidence.anomaly_type == "nearfull"
assert evidence.kg_analysis.top_k_paths == []
```

Base:

```python
record = {
    "dataset": "mvtec",
    "object": "bottle",
    "defect_type": "scratch",
    "mask_stats": {"area_ratio": 0.16, "eccentricity": 0.93},
}
evidence = evidence_from_mvtec_record(record)
assert evidence.morphology == "linear"
```

Bad:

```python
record = {
    "dataset": "mvtec",
    "defect_type": "scratch",
    "root_cause": "HandlingDamage",
}
evidence = evidence_from_mvtec_record(record)
assert "root_cause" not in evidence.raw_evidence.extra
```

### 6. Tests Required

Adapter tests must assert:

- returned object is schema-valid `Evidence`,
- adapter metadata identifies the adapter and has `produces_root_cause=False`,
- `kg_analysis` is empty,
- observations have stable IDs and source/raw provenance,
- root-cause/path-ranking keys are removed recursively,
- WM811K remains `dataset="wafer"` while identifying `adapter.name="wm811k"`,
- deterministic fallback fields are produced from mask or wafer-map descriptors,
- batch dispatch routes explicit WM811K wafer records to the WM811K adapter.

Run at minimum:

```bash
uv run --extra dev pytest tests/test_adapters.py
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
uv run python scripts/run_examples.py
```

### 7. Wrong vs Correct

#### Wrong

```python
def evidence_from_mvtec_record(record):
    evidence = Evidence(...)
    evidence.kg_analysis.top_k_paths = record["top_k_paths"]
    return evidence
```

This makes the adapter a reasoning module and can leak answers into inputs.

#### Correct

```python
def evidence_from_mvtec_record(record):
    return Evidence(
        ...,
        adapter=adapter_metadata("mvtec"),
        kg_analysis=KGAnalysis(),
    )
```

Then call:

```python
result = KGTracePipeline().analyze(evidence)
```

#### Wrong

```python
def evidence_from_wm811k_record(record):
    return Evidence(dataset="wm811k", ...)
```

This creates schema and KG scenario churn before the project supports a new
dataset literal.

#### Correct

```python
def evidence_from_wm811k_record(record):
    return Evidence(
        dataset="wafer",
        adapter=adapter_metadata(
            "wm811k",
            metadata={"source_dataset": "wm811k", "schema_dataset": "wafer"},
        ),
        ...
    )
```

## Scenario: Model-Dependent Producer Records

### 1. Scope / Trigger

- Trigger: implementing or changing code that runs models over local dataset
  samples and emits producer-output records.
- Applies to `src/kgtracevis/producers/` and
  `scripts/build_dataset_records.py`.
- Reason: producers are allowed to be model-dependent, but their output still
  must be observed evidence records consumed by Evidence adapters. They must not
  become KG reasoning or RCA modules.

### 2. Signatures

Producer helper examples:

```python
def build_mvtec_records(
    input_root: str | Path,
    predictor: MVTecAnomalyPredictor,
    *,
    output_dir: str | Path | None = None,
    model_backend: str = "local",
    checkpoint: str | Path | None = None,
    threshold: float = 0.5,
    max_cases: int | None = None,
    max_per_label: int | None = None,
    seed: int | None = None,
    include_good: bool = False,
) -> list[dict[str, Any]]:
    ...

def build_wm811k_records(
    input_path: str | Path,
    classifier: WM811KClassifier,
    *,
    output_dir: str | Path | None = None,
    model_backend: str = "local",
    checkpoint: str | Path | None = None,
    threshold: float | None = None,
    max_cases: int | None = None,
    max_per_label: int | None = None,
    seed: int | None = None,
    include_unlabeled: bool = False,
) -> list[dict[str, Any]]:
    ...
```

CLI shape:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_subset.jsonl \
  --model-backend anomalib-torch \
  --checkpoint data/external/checkpoints/mvtec_patchcore.pt \
  --overwrite
```

### 3. Contracts

Producer layer:

- Emits plain record dictionaries or JSONL, not `Evidence`.
- Must not import or call `KGTracePipeline`.
- Must recursively filter forbidden reasoning-output keys before writing JSONL.
- May run local model inference, save heatmaps/masks/saliency maps under ignored
  paths, and attach model/checkpoint metadata.
- Must keep raw datasets, generated records, and checkpoints out of Git.

MVTec producer records:

- Use `dataset="mvtec"`.
- Include image path, object/category, defect label when available, model
  score/confidence, generated heatmap or mask path when available, mask stats,
  and detector metadata.
- Optional Anomalib backends are runtime-only imports; tests must not require
  Anomalib or checkpoints.

WM811K producer records:

- Use `dataset="wafer"` and `adapter="wm811k"`.
- Include predicted pattern, classification confidence, descriptor stats,
  native label provenance when available, and classifier metadata.
- Local sklearn/joblib checkpoints are trusted-local only; never load untrusted
  pickle/joblib files.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Producer output contains root-cause/path-ranking keys | Remove them recursively before JSONL write |
| Real backend requires checkpoint but none is provided | Raise `ValueError` naming the missing checkpoint |
| Optional Anomalib backend is selected but package is unavailable | Raise `ImportError` explaining to install Anomalib or use fake backend |
| WM811K wafer map is not 2D | Raise `ValueError` |
| Valid model score/confidence is `0.0` | Preserve `0.0`; do not treat as missing |
| sklearn checkpoint load fails | Raise an error mentioning trusted-local joblib/pickle boundary |
| Generated records are ready | Validate through existing `evidence_from_records` and adapter pipeline |

### 5. Good/Base/Bad Cases

Good:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input data/external/wafer/LSWMD.pkl \
  --output-jsonl data/processed/records/wm811k_subset.jsonl \
  --model-backend sklearn \
  --checkpoint data/external/checkpoints/wm811k_classifier.joblib \
  --overwrite
```

Base:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root tests/fixtures/mvtec_tiny \
  --output-jsonl /tmp/mvtec_records.jsonl \
  --model-backend fake \
  --overwrite
```

Bad:

```python
records = KGTracePipeline().analyze(evidence)
```

Producer modules must not run KG reasoning. They stop at record generation.

### 6. Tests Required

Tests must assert:

- fake predictors can exercise producer contracts without checkpoints,
- generated MVTec and WM811K records validate through `evidence_from_records`,
- forbidden reasoning-output keys are filtered recursively,
- valid zero scores/confidences are preserved,
- malformed wafer maps fail explicitly,
- Anomalib wrapper can normalize injected fake inferencer outputs,
- sklearn wrapper can load a tiny trusted local model and call `predict` /
  `predict_proba`,
- CLI backend selection works without real Anomalib installed.

Run at minimum:

```bash
uv run --extra dev pytest tests/test_record_producers.py
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
```

### 7. Wrong vs Correct

#### Wrong

```python
record = {
    "case_id": case_id,
    "root_cause": model.predict_root_cause(image),
}
```

This mixes producer inference with RCA authority.

#### Correct

```python
record = {
    "case_id": case_id,
    "dataset": "mvtec",
    "confidence": prediction.score,
    "heatmap_path": str(heatmap_path),
    "detector": {"backend": "anomalib-torch", "checkpoint": str(checkpoint)},
}
```

Runtime KG analysis happens later through the existing adapter pipeline.

## Scenario: Adapter-to-Pipeline Experiment Outputs

### 1. Scope / Trigger

- Trigger: implementing or changing commands that convert producer-output
  records into Evidence, run `KGTracePipeline`, and write experiment artifacts.
- Applies to `scripts/run_adapter_pipeline.py`,
  `src/kgtracevis/experiments/adapter_pipeline.py`, and suite stages that call
  them.
- Reason: these artifacts are close to paper tables; they must preserve
  provenance and claim boundaries rather than becoming implicit RCA labels.

### 2. Signatures

Reusable helper signature:

```python
def run_adapter_pipeline(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    dataset: DatasetName | None = None,
    top_k: int = 5,
    overwrite: bool = False,
    pipeline: KGTracePipeline | None = None,
) -> AdapterPipelineOutput:
    ...
```

CLI shape:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/mvtec_records.jsonl \
  --dataset mvtec \
  --output-dir outputs/adapter_pipeline_v0/mvtec \
  --top-k 5 \
  --overwrite
```

### 3. Contracts

Inputs:

- `--input` accepts normalized producer-output records in `.json`, `.jsonl`,
  or `.csv` form.
- `--dataset` is optional for records that carry enough dataset/adapter
  metadata; WM811K should still use `--dataset wafer`.
- `--top-k` must be at least 1.
- `--overwrite` is required to replace an existing summary/table.

Outputs:

- `evidence/` contains generated Evidence JSON files with empty adapter-level
  `kg_analysis` before runtime analysis.
- `adapter_pipeline_summary.json` contains case summaries, linked entities,
  consistency, correction candidates, `top_k_paths`, source edge provenance,
  and candidate/plausible explanation targets.
- `adapter_pipeline_table.csv` contains compact paper-review rows including
  `explanation_scope` and `claim_boundary`.
- `explanation_scope` must remain
  `candidate_plausible_explanation_not_verified_rca` for current MVTec and
  WM811K outputs unless references are externally upgraded.

Suite integration:

- `scripts/run_experiment_suite.py` may run MVTec and WM811K adapter pipeline
  stages, but generated `runs/`/`outputs/` artifacts remain ignored until
  reviewed and copied to `paper/`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| `top_k < 1` | Raise `ValueError` |
| Summary/table exists and `overwrite=False` | Raise `FileExistsError` |
| Record cannot be converted to `Evidence` | Let adapter/schema validation fail |
| WM811K command uses `--dataset wafer` | Output rows use `dataset="wafer"` and `adapter_name="wm811k"` |
| Top-k path targets are produced for MVTec/WM811K | Label them as candidate/plausible explanations, not verified RCA |
| Suite records multiple output files | Include both summary JSON and CSV table in `output_paths` |

### 5. Good/Base/Bad Cases

Good:

```bash
uv run python scripts/run_experiment_suite.py
# table_summary.csv includes adapter_pipeline_mvtec and adapter_pipeline_wm811k
# output paths include both adapter_pipeline_summary.json and adapter_pipeline_table.csv
```

Base:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_v0/wm811k \
  --overwrite
```

Bad:

```text
adapter_pipeline_table.csv column: verified_root_cause=GlueRemovalInsufficient
```

Current MVTec/WM811K adapter-pipeline tables must not add verified RCA columns
or wording.

### 6. Tests Required

Tests must assert:

- helper writes Evidence files, summary JSON, and CSV table,
- CLI reports summary path, table path, evidence count, case count, and scope,
- existing outputs are protected unless `overwrite=True`,
- WM811K rows keep `dataset="wafer"` and `adapter_name="wm811k"`,
- top target/path rows include `explanation_scope` and `claim_boundary`,
- experiment suite includes both adapter pipeline stages and output paths.

Run at minimum:

```bash
uv run --extra dev pytest tests/test_adapter_pipeline.py tests/test_experiment_suite.py
uv run --extra dev ruff check .
```

### 7. Wrong vs Correct

#### Wrong

```python
row = {"case_id": case_id, "root_cause": top_target_name}
```

This turns a source-constrained candidate path into a verified RCA label.

#### Correct

```python
row = {
    "case_id": case_id,
    "top_target_name": top_target_name,
    "explanation_scope": "candidate_plausible_explanation_not_verified_rca",
    "claim_boundary": "candidate/plausible explanation only",
}
```

The row remains useful for paper review without overstating evidence strength.

## Scenario: Paper-Facing Experiment Manifests

### 1. Scope / Trigger

- Trigger: implementing or changing paper-facing manifest/table builders that
  summarize generated experiment outputs.
- Applies to `src/kgtracevis/experiments/paper_tables.py` and
  `scripts/build_paper_tables.py`.
- Reason: manifest outputs bridge reproducibility artifacts and paper drafting;
  they must preserve grouping fields, source commands, and claim boundaries.

### 2. Signatures

Reusable helper signature:

```python
def build_paper_tables(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    adapter_summary_paths: Sequence[str | Path] = DEFAULT_ADAPTER_SUMMARY_PATHS,
    noise_summary_path: str | Path = DEFAULT_NOISE_SUMMARY_PATH,
    suite_summary_path: str | Path = DEFAULT_SUITE_SUMMARY_PATH,
    examples_dir: str | Path = "data/examples",
    references_dir: str | Path = "data/references",
    overwrite: bool = False,
) -> PaperTablesOutput:
    ...
```

CLI shape:

```bash
uv run python scripts/build_paper_tables.py --overwrite
```

### 3. Contracts

Inputs:

- adapter pipeline summaries from `runs/v0_experiment_suite/adapter_pipeline_*`,
- noise experiment summary from `runs/v0_examples/summary.json`,
- suite summary from `runs/v0_experiment_suite/summary.json`,
- checked-in examples and reference CSVs for dataset and annotation-type lookup.

Outputs under the selected ignored output directory:

- `paper_manifest.csv` groups rows by `dataset`, `noise_type`,
  `annotation_type`, and `metric_scope`,
- `command_manifest.csv` records suite stage, source command, output paths, and
  claim boundary,
- `paper_tables_summary.json` records source artifacts and row counts.

The builder must not write into `paper/` automatically. Copying a selected
table into `paper/tables/` is a later human-reviewed step.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
| --- | --- |
| Output files exist and `overwrite=False` | Raise `FileExistsError` |
| Optional adapter/noise/suite artifact is missing | Skip that source and write rows from available sources |
| Example JSON cannot be parsed while indexing | Skip that example rather than failing the manifest build |
| Reference CSV has no `case_id` | Ignore that row |
| Suite command has output paths | Copy them into command provenance rows |
| MVTec/WM811K path-derived rows are present | Preserve candidate/plausible claim boundary |

### 5. Good/Base/Bad Cases

Good:

```bash
uv run python scripts/run_experiment_suite.py
uv run python scripts/build_paper_tables.py --overwrite
```

Base:

```bash
uv run python scripts/build_paper_tables.py \
  --noise-summary runs/v0_examples/summary.json \
  --suite-summary runs/v0_experiment_suite/summary.json \
  --overwrite
```

Bad:

```text
paper_manifest.csv copied automatically into paper/tables/ as final results
```

Generated manifest rows are review inputs, not automatically selected paper
assets.

### 6. Tests Required

Tests must assert:

- manifest and command CSVs plus summary JSON are written,
- rows include dataset, noise type, annotation type, metric scope, source
  artifact, source command, counts, and claim boundary,
- adapter, noise, and suite command sources all contribute rows,
- existing outputs require `overwrite=True`,
- CLI prints generated paths and row counts.

Run at minimum:

```bash
uv run --extra dev pytest tests/test_paper_tables.py
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
```

### 7. Wrong vs Correct

#### Wrong

```python
paper_table_path = Path("paper/tables/results.csv")
write_manifest(paper_table_path)
```

This bypasses the human review step for selected paper assets.

#### Correct

```python
output_dir = Path("artifacts/paper_tables_v0")
build_paper_tables(output_dir=output_dir, overwrite=True)
```

The generated manifest stays under ignored artifacts until reviewed.
