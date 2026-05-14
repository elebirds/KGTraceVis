# Optimize Evidence Schema / Adapter Layer

## Goal

Make small, high-confidence improvements to the KGTraceVis evidence schema and dataset adapter layer so validation, metadata preservation, provenance, and adapter edge cases are clearer and more robust.

## Requirements

- Keep work scoped to:
  - `src/kgtracevis/schema/evidence_schema.py`
  - `src/kgtracevis/schema/validators.py`
  - `src/kgtracevis/adapters/*.py`
  - `tests/test_schema.py`
  - `tests/test_adapters.py`
  - `tests/test_batch_adapters.py`
  - `docs/evidence_schema.md` only if behavior changes need documentation
- Do not modify producers, core pipeline, KG modules, service/API, web, or KG construction files.
- Preserve unified anomaly evidence schema compatibility across `mvtec`, `tep`, and `wafer`.
- Prefer narrow hardening around schema validation, metadata preservation, forbidden reasoning-output filtering, stable observation IDs/provenance, and adapter edge cases.
- If no safe code change is found, strengthen focused tests documenting current behavior.

## Acceptance Criteria

- Evidence schema and adapters remain backward compatible for existing tests.
- Any new validation/filtering behavior is covered by focused tests.
- Required verification passes:
  - `uv run --extra dev pytest tests/test_schema.py tests/test_adapters.py tests/test_batch_adapters.py`
  - `uv run --extra dev ruff check src/kgtracevis/schema src/kgtracevis/adapters tests/test_schema.py tests/test_adapters.py tests/test_batch_adapters.py`
  - `uv run --extra dev mypy src/kgtracevis/schema src/kgtracevis/adapters`

## Out of Scope

- Producer changes.
- Core pipeline, KG, service/API, web, KG construction, or runtime store changes.
- Broad schema redesign or dataset-specific schema variants.
