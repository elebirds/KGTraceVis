# Implement Noise and Metrics V0

## Goal

Implement the first reproducible noise-and-metrics loop for KGTraceVis.

The task should turn the current placeholders into a small, deterministic v0
that can corrupt checked-in example evidence, run the existing pipeline, compute
core evaluation metrics, and emit a compact experiment summary without adding a
large experiment framework.

## What I Already Know

- `src/kgtracevis/noise/noise_injector.py` is currently a placeholder.
- `src/kgtracevis/metrics/*.py` files are placeholders.
- `scripts/run_noise_experiment.py` is a placeholder that mentions
  `configs/noise_config.yaml`.
- `configs/noise_config.yaml` defines:
  - `seed: 42`
  - `noise_levels: [0.1, 0.2, 0.3]`
  - supported noise types:
    - `anomaly_type_replacement`
    - `location_replacement`
    - `morphology_replacement`
    - `variable_deletion`
    - `variable_name_perturbation`
    - `log_event_deletion`
    - `synonym_substitution`
    - `contradiction_injection`
- `configs/experiment_config.yaml` defines:
  - `experiment_name: v0_examples`
  - `input_dir: data/examples`
  - `output_dir: runs`
  - `top_k: 5`
- Example evidence files already cover MVTec, TEP, and wafer.
- `KGTracePipeline.analyze()` now returns stable linked entity, correction, path,
  and source edge references.

## Assumptions

- Noise injection should operate on `Evidence` objects and return a new
  `Evidence`; it must not mutate the input object.
- Noise metadata should live in `raw_evidence.extra` for v0 rather than changing
  the evidence schema.
- For v0, replacement pools can be deterministic and local to the module,
  drawing from known example/KG-friendly labels.
- Metrics should be standalone pure functions with simple Python inputs/outputs.
- Experiment outputs should go under ignored runtime directories such as `runs/`
  and should not require committing generated files.

## Requirements

### Noise Injection

- Implement deterministic field-level corruption with fixed seeds.
- Support these v0 noise types:
  - anomaly type replacement,
  - location replacement,
  - morphology replacement,
  - variable deletion,
  - variable name perturbation,
  - log event deletion,
  - synonym substitution,
  - contradiction injection.
- Always record noise metadata:
  - `is_noisy`,
  - `noise_level`,
  - `noise_type`,
  - `corrupted_fields`,
  - `clean_reference`.
- Preserve the original clean evidence by value in `clean_reference`.
- Return valid `Evidence` objects after corruption.
- Use stable deterministic behavior for the same evidence, noise type, level,
  and seed.

### Metrics

Implement standalone metric functions for:

- schema validity rate,
- entity linking accuracy,
- top-k linking accuracy,
- inconsistency detection precision/recall,
- correction accuracy,
- top-k correction accuracy,
- noise recovery rate,
- top-k root-cause accuracy,
- mean reciprocal rank,
- path hit rate.

The functions should be small and accept plain collections such as labels,
predictions, records, or pipeline result dictionaries. Do not tie metric
computation to Streamlit or script output formatting.

### Experiment Script

- Update `scripts/run_noise_experiment.py` to:
  - read config from `configs/noise_config.yaml` and
    `configs/experiment_config.yaml`,
  - load example evidence from `input_dir`,
  - run clean pipeline analysis,
  - generate noisy evidence for configured levels/noise types,
  - run noisy pipeline analysis,
  - compute a compact metrics summary,
  - write JSON output under `runs/<experiment_name>/` or a timestamped child,
  - print a short CLI summary.
- The script must not require Neo4j or external datasets.
- The script should be deterministic when configs use the same seed.

## Acceptance Criteria

- [x] Noise injection is deterministic for the same input and seed.
- [x] Noise injection records all required metadata in `raw_evidence.extra`.
- [x] Noise injection does not mutate the original `Evidence`.
- [x] Tests cover at least one visual field corruption and one list-field
  corruption.
- [x] Metric functions cover base/good/bad cases, including empty inputs where
  applicable.
- [x] `scripts/run_noise_experiment.py` runs locally against `data/examples`.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.

## Out Of Scope

- No formal paper experiment claims yet.
- No large external dataset loading.
- No generated run artifacts committed to git.
- No Neo4j dependency.
- No Streamlit UI integration.
- No new KG facts.

## Technical Notes

- Expected implementation files:
  - `src/kgtracevis/noise/noise_injector.py`
  - `src/kgtracevis/metrics/detection_metrics.py`
  - `src/kgtracevis/metrics/linking_metrics.py`
  - `src/kgtracevis/metrics/correction_metrics.py`
  - `src/kgtracevis/metrics/ranking_metrics.py`
  - `scripts/run_noise_experiment.py`
  - focused tests under `tests/`
- Preserve current pipeline contracts from the completed
  `harden-pipeline-output-contracts` task.
