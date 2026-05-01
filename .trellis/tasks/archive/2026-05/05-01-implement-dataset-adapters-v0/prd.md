# Implement Dataset Adapters V0

## Goal

Implement small dataset adapter helpers for MVTec/DS-MVTec, TEP, and wafer data
that produce validated unified `Evidence` objects.

The adapters should make downstream scripts and future experiments consume the
same schema without creating dataset-specific JSON variants.

## What I Already Know

- `src/kgtracevis/adapters/ds_mvtec_adapter.py`,
  `src/kgtracevis/adapters/tep_adapter.py`, and
  `src/kgtracevis/adapters/wafer_adapter.py` are placeholders.
- The unified schema lives in `src/kgtracevis/schema/evidence_schema.py`.
- Existing checked-in example JSON files validate for `mvtec`, `tep`, and
  `wafer`.
- Dataset-specific details must remain under `raw_evidence` or
  `raw_evidence.extra`.
- This task follows the roadmap after pipeline contracts and noise/metrics v0.

## Assumptions

- V0 adapters can accept dictionaries or explicit keyword arguments rather than
  full external dataset directories.
- File/path existence checks should be lightweight; adapters should preserve
  paths as raw evidence metadata rather than loading large images/tables.
- MVTec mask-derived geometry can be a simple optional helper based on provided
  bounding box or region metadata; do not add OpenCV/Pillow logic in this task.
- TEP and wafer adapters should support the minimal fields needed by current KG
  linking and pipeline examples.

## Requirements

### Shared Adapter Behavior

- Return `Evidence` objects validated by Pydantic.
- Preserve unknown dataset-specific fields in `raw_evidence.extra`.
- Use `null` / `"unknown"` consistently when values are not known.
- Do not create dataset-specific evidence schemas.
- Do not mutate caller-provided input dictionaries.

### MVTec / DS-MVTec Adapter

- Provide a public function to create evidence from an MVTec-style record.
- Capture at least:
  - object name,
  - defect/anomaly type,
  - optional location,
  - optional morphology,
  - optional severity/confidence,
  - optional image/mask/heatmap paths,
  - optional description/caption.
- Store image/mask/heatmap/path details in `raw_evidence.extra`.

### TEP Adapter

- Provide a public function to create evidence from a TEP-style record.
- Capture at least:
  - fault/anomaly type,
  - process object/location,
  - variables,
  - variable contributions,
  - severity/confidence,
  - optional timestamp/description.
- Store TEP-specific fault IDs/run/window metadata in `raw_evidence.extra`.

### Wafer Adapter

- Provide a public function to create evidence from a wafer-style record.
- Capture at least:
  - wafer object,
  - defect/anomaly type,
  - location,
  - morphology,
  - log events,
  - severity/confidence,
  - optional image/log/process metadata.
- Store wafer/process-specific details in `raw_evidence.extra`.

## Acceptance Criteria

- [x] Each adapter returns a valid `Evidence` object.
- [x] Tests cover representative MVTec, TEP, and wafer records.
- [x] Tests assert caller input dictionaries are not mutated.
- [x] Tests assert dataset-specific details live in `raw_evidence.extra`.
- [x] Existing example validation and pipeline tests still pass.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.

## Out Of Scope

- No full raw dataset loaders.
- No image/mask file parsing.
- No new schema variants.
- No KG fact additions.
- No Streamlit integration.

## Technical Notes

- Expected implementation files:
  - `src/kgtracevis/adapters/ds_mvtec_adapter.py`
  - `src/kgtracevis/adapters/tep_adapter.py`
  - `src/kgtracevis/adapters/wafer_adapter.py`
  - `src/kgtracevis/adapters/__init__.py`
  - focused tests under `tests/`
