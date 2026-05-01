# Build Batch Evidence Generation V0

## Goal

Add AI-owned batch evidence generation tooling so curated records can be
converted into unified `Evidence` JSON files without hand-writing one example at
a time.

This task should build on existing MVTec/TEP/wafer single-record adapters and
stay clear of human RCA ground-truth decisions.

## What I Already Know

- `src/kgtracevis/adapters/*_adapter.py` already converts one record dictionary
  into a validated `Evidence` object.
- Adapter tests already cover MVTec, TEP, wafer, input immutability, and
  `raw_evidence.extra` preservation.
- `configs/paths.yaml` defines `data/examples`, `data/processed`, `runs`, and
  `outputs` directories.
- Current experiment automation consumes Evidence JSON files from directories.
- Missing piece: a reusable batch loader/writer that can turn CSV/JSON/JSONL
  records into evidence files for downstream scripts.

## Requirements

- Add reusable batch adapter helpers under `src/kgtracevis/adapters/`.
- Support input formats:
  - JSON list of records,
  - JSON object containing `records`,
  - JSONL,
  - CSV.
- Support dataset selection:
  - explicit CLI `--dataset {mvtec,tep,wafer}`,
  - or per-record `dataset` when no explicit dataset is supplied.
- Return validated `Evidence` objects.
- Write outputs as either:
  - one JSON file per evidence under an output directory,
  - or one JSONL file containing all generated evidence.
- Produce a compact summary with counts by dataset/source.
- Do not mutate input records.
- Do not read large raw image/time-series files; preserve paths as metadata.

## CLI

Add `scripts/generate_evidence.py` with:

- `--input <path>`
- `--dataset <mvtec|tep|wafer>` optional
- `--output-dir <dir>` optional for per-case JSON
- `--output-jsonl <path>` optional for JSONL
- `--overwrite` optional

At least one output destination is required.

## Acceptance Criteria

- [x] Batch helpers load JSON, JSONL, and CSV records.
- [x] Batch helpers dispatch to the correct dataset adapters.
- [x] CLI writes per-case JSON evidence files.
- [x] CLI writes JSONL evidence output.
- [x] Summary includes total count and counts by dataset/source.
- [x] Tests cover MVTec/TEP/wafer batch conversion.
- [x] Tests cover no input mutation and overwrite protection.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.
- [x] CLI smoke output can be consumed by `scripts/run_examples.py`.

## Out Of Scope

- No automatic image/mask parsing.
- No external dataset download.
- No RCA labels or KG facts.
- No paper-grade experiment claims.

## Technical Notes

- Likely files:
  - `src/kgtracevis/adapters/batch.py`
  - `scripts/generate_evidence.py`
  - `tests/test_batch_adapters.py`
  - optional README/docs update for command usage.
