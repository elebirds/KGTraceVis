# Calibrated MVTec Amazon PatchCore Pipeline

## Goal

Provide a one-command calibrated MVTec Amazon PatchCore pipeline for paper and
demo artifacts. The command should reuse existing calibration thresholds and
produce bounded, reproducible outputs without re-running calibration.

## Requirements

* Add reusable orchestration logic under `src/kgtracevis/experiments/` or a
  nearby package module.
* Build a bounded DS-MVTec/MVTec-like sample input from a dataset root using
  object and per-label count limits.
* Run `AmazonPatchCoreObjectRouter` with an existing threshold config.
* Write producer records JSONL.
* Run the adapter and `KGTracePipeline` over those records.
* Write compact summary/table artifact paths for paper/demo use.
* Add a CLI script such as `scripts/run_mvtec_calibrated_pipeline.py` with
  `dataset-root`, `artifact-root`, `threshold-config`, `output-root`,
  `objects`/`max-objects`, `max-good`, `max-defect-per-label`, `device`,
  `overwrite`, and `top-k` arguments.
* Use existing helpers where possible, but keep reusable logic out of scripts.
* Do not re-run calibration unless explicitly requested.
* Add focused tests using fake predictors/helper functions, not real model
  execution.
* Update docs briefly.
* Do not commit.

## Acceptance Criteria

* [x] A single CLI command can produce producer JSONL, adapter/KGTrace outputs,
  and compact summary/table artifacts from a bounded MVTec sample.
* [x] The reusable implementation lives under `src/kgtracevis/` and scripts are
  thin clients.
* [x] Tests cover the orchestration with fakes and do not require Amazon
  PatchCore checkpoints or real image inference.
* [x] Documentation describes the command and clarifies that calibration is not
  re-run.

## Definition of Done

* Tests added or updated for the new reusable logic.
* Relevant focused test suite run.
* Docs updated for user-facing command behavior.
* Worktree changes remain uncommitted.

## Technical Approach

Implement a small experiment orchestrator that composes existing MVTec sample
selection, Amazon PatchCore producer, adapter, and `KGTracePipeline` APIs. Keep
filesystem and table-writing behavior deterministic and overwrite-aware. The CLI
will parse arguments, call the reusable orchestrator, and print the resulting
artifact paths.

## Out of Scope

* Re-running threshold calibration.
* Downloading datasets or checkpoints.
* Running real model inference in unit tests.
* Changing KG ontology, evidence schema, or calibration semantics.

## Technical Notes

* Follow `.trellis/spec/backend/` guidance for directory structure, adapters,
  MVTec model presets, logging, and quality.
* User explicitly requested the committed baseline be respected and no commit be
  created.

## Implementation Notes

Implemented:

* `src/kgtracevis/experiments/mvtec_calibrated_pipeline.py`
* `scripts/run_mvtec_calibrated_pipeline.py`
* shared DS-MVTec subset builder in `src/kgtracevis/experiments/mvtec_patchcore.py`
* README/spec command documentation
* focused tests in `tests/test_mvtec_patchcore_experiment.py`

Verified real one-command run:

```text
summary_path=runs/mvtec_calibrated_pipeline/mvtec_calibrated_pipeline_summary.json
records_path=runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl
adapter_summary=runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_summary.json
adapter_table=runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_table.csv
record_count=86
adapter_case_count=86
object_count=15
defect_pred_anomalous=71/71
good_pred_normal=14/15
```

Quality gates:

```text
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
uv run --extra dev pytest -q  # 164 passed
uv run python scripts/run_examples.py
```
