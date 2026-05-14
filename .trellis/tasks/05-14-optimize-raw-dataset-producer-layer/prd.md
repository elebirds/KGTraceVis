# implement: optimize raw dataset producer layer

## Goal

Make small, high-confidence robustness and usability improvements to the raw
dataset producer layer for MVTec, WM811K, and TEP while preserving the producer
boundary: producers emit adapter-ready raw records and do not perform RCA or KG
reasoning.

## What I Already Know

- Work is in `/Users/hhm/code/KGTraceVis`.
- Write scope is limited to:
  - `src/kgtracevis/producers/*.py`
  - `src/kgtracevis/workflows/dataset_records.py`
  - `scripts/build_dataset_records.py`
  - `tests/test_record_producers.py`
  - `docs/dataset_record_producers.md` only if needed
- Do not modify adapters/schema, core pipeline/KG modules, service/API, web, or
  KG construction files.
- Preferred improvements include parameter validation, TEP raw CSV edge cases,
  clearer CLI errors, forbidden-output filtering, deterministic sampling, and
  docs/tests proving records remain adapter-ready.

## Requirements

- Keep producers as raw record producers.
- Do not add RCA, KG reasoning, or dataset-specific evidence schema logic.
- Preserve adapter-ready output contracts.
- Avoid touching files outside ownership unless absolutely necessary.
- Respect existing user/agent edits in the worktree.

## Acceptance Criteria

- [ ] Robustness/usability improvement implemented in producer/workflow/script
      layer.
- [ ] Tests cover the behavior.
- [ ] Required verification passes:
      `uv run --extra dev pytest tests/test_record_producers.py`
- [ ] Required lint passes:
      `uv run --extra dev ruff check src/kgtracevis/producers src/kgtracevis/workflows/dataset_records.py scripts/build_dataset_records.py tests/test_record_producers.py`
- [ ] Required type check passes:
      `uv run --extra dev mypy src/kgtracevis/producers src/kgtracevis/workflows/dataset_records.py scripts/build_dataset_records.py`

## Out of Scope

- Adapter/schema changes.
- Core KG/RCA/path-ranking changes.
- Service/API/web changes.
- KG construction or industrial fact additions.

## Technical Notes

- Follow `.trellis/spec/backend/adapter-guidelines.md`,
  `.trellis/spec/backend/workflow-architecture.md`,
  `.trellis/spec/backend/error-handling.md`,
  `.trellis/spec/backend/quality-guidelines.md`, and shared thinking guides.
