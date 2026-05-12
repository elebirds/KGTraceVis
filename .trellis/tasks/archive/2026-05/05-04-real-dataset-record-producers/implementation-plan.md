# Implementation Plan: Real Dataset Model Producers

Date: 2026-05-04

## Milestone Goal

Move from checked-in fixture records to reproducible model-output records for
real MVTec/DS-MVTec and WM811K subsets, while preserving the adapter-first
architecture:

```text
raw local data -> model inference -> producer-output records -> Evidence adapters -> KGTracePipeline
```

## Recommended Implementation Order

### Step 1: Producer Package Skeleton

Files:

- `src/kgtracevis/producers/__init__.py`
- `src/kgtracevis/producers/common.py`
- `src/kgtracevis/producers/mvtec_records.py`
- `src/kgtracevis/producers/wm811k_records.py`
- `tests/test_record_producers.py`

Tasks:

- Add shared JSONL writer, deterministic sampling helper, and predictor
  protocol/type aliases.
- Add root-cause/path-output key filtering at producer boundary too, mirroring
  adapter safeguards.
- Return plain record dictionaries, not `Evidence`.

Acceptance:

- Unit tests can build records from tiny in-test structures with fake
  predictors.
- No producer imports `KGTracePipeline`.

### Step 2: MVTec Producer

Tasks:

- Support standard MVTec-like directory roots.
- Accept a predictor object/backend that returns image-level score plus optional
  anomaly map/mask path or array.
- Discover anomalous image files under object/defect folders.
- Pair masks when a ground-truth/mask path exists.
- Run per-image inference and generate stable `case_id`, `object`,
  `defect_type`, `image_path`, model `confidence`, generated `heatmap_path` or
  `mask_path`, `mask_stats`, and metadata.
- Save generated model outputs under ignored processed/interim paths.

Acceptance:

- Tiny synthetic directory fixture produces deterministic records using a fake
  predictor.
- Generated records validate through `evidence_from_records(..., dataset="mvtec")`.

### Step 3: WM811K Producer

Tasks:

- Support a small pandas-readable table fixture first.
- Accept a classifier/predictor object/backend that returns predicted pattern,
  confidence, and optional saliency/attention output.
- Support common WM811K fields: `waferMap`, `failureType`, `lotName`,
  `waferIndex`.
- Normalize predicted pattern labels into adapter-compatible `failure_pattern`;
  keep native labels separately for evaluation.
- Compute descriptor stats with existing wafer-map helper functions.
- Add class-balanced deterministic `max_per_label` selection.

Acceptance:

- Tiny synthetic table produces deterministic records using a fake predictor.
- Generated records validate through `evidence_from_records(..., dataset="wafer")`.

### Step 4: Thin CLI

Files:

- `scripts/build_dataset_records.py`
- `configs/dataset_records.example.yaml`

Tasks:

- Add one CLI with `--dataset`, `--input-root` or `--input`, `--output-jsonl`,
  `--model-backend`, `--checkpoint`, `--threshold`, `--max-cases`,
  `--max-per-label`, `--seed`, `--overwrite`.
- Keep config support minimal: direct flags plus an optional example YAML path.
- Print a compact JSON summary with record count, dataset, labels, output path,
  and claim boundary.

Acceptance:

- CLI can build MVTec and WM811K records from test fixtures using fake/local
  backends.
- Existing `scripts/run_adapter_pipeline.py` can consume the generated JSONL.

### Step 5: Documentation and Smoke Path

Files:

- `README.md`
- `docs/adapter_contracts.md` or a new `docs/dataset_record_producers.md`
- `docs/experiment_plan.md`

Tasks:

- Document where to place local datasets under `data/external/`.
- Document producer commands and the follow-up adapter pipeline commands.
- Reiterate that producer records contain observations and labels only, never
  verified RCA for MVTec/WM811K.

Acceptance:

- A new user can see the path from local raw data to `paper_manifest.csv`.

## Suggested First Implementation Batch

Implement:

1. producer package skeleton and predictor protocols,
2. deterministic sampling and JSONL writer,
3. WM811K table producer with fake classifier fixture test,
4. MVTec folder producer with fake anomaly detector fixture test,
5. CLI with direct flags and backend/checkpoint metadata.

Defer:

- heavy training loops,
- parquet support if optional engines are unavailable,
- production-grade Anomalib/PyTorch wrapper polish beyond one local backend,
- TEP producer.

## Quality Gate

Run:

```bash
uv run --extra dev pytest tests/test_record_producers.py
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
uv run python scripts/run_examples.py
```

Smoke command after implementation:

```bash
uv run python scripts/build_dataset_records.py --dataset mvtec ...
uv run python scripts/build_dataset_records.py --dataset wm811k ...
uv run python scripts/run_adapter_pipeline.py --input <generated-jsonl> --dataset <mvtec|wafer> ...
```
