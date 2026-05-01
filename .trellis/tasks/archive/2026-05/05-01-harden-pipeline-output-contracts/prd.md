# Harden Pipeline Output Contracts

## Goal

Make the current v0 pipeline outputs stable and feedback-compatible before
building metrics, experiments, Streamlit UI, or service handlers on top of them.

The task should tighten output behavior without changing the research scope or
introducing a new backend.

## What I Already Know

- `KGTracePipeline.analyze()` already runs linking, consistency checking,
  correction candidate generation, and path ranking.
- `AnalysisResult` is currently a Pydantic envelope with loose `list[dict]`
  fields.
- Linked entities already include field, mention, selected entity ID, score,
  match type, ambiguity, and candidate lists.
- Correction candidates already include stable-looking `candidate_id` values
  and supporting KG edge dumps.
- Ranked paths already include stable-looking `path_id` values, node/relation
  sequences, scores, supporting evidence, and source edge dumps.
- Existing tests assert that outputs exist, but do not yet protect output
  contract details.
- Downstream planned work needs these contracts:
  - metrics need stable IDs and target/source fields,
  - Streamlit needs predictable serializable structures,
  - feedback needs correction/path/entity/KG edge references.

## Assumptions

- Keep the in-memory KG as the default backend.
- Keep output payloads JSON-serializable and Pydantic-compatible.
- Do not introduce dataset-specific result schemas.
- Prefer focused tests over a large model refactor unless the implementation
  agent finds a simple typed model pattern that fits the existing code.

## Requirements

- Ensure `AnalysisResult` can be serialized with all pipeline outputs intact.
- Preserve stable identifiers for:
  - correction candidates,
  - ranked paths,
  - KG source edges,
  - selected linked entities.
- Ensure ranked paths expose enough information for feedback and visual review:
  - `path_id`,
  - node sequence,
  - relation sequence,
  - score,
  - supporting evidence,
  - source edges.
- Ensure correction candidates expose enough information for feedback and review:
  - `candidate_id`,
  - target field,
  - original value,
  - suggested value/entity,
  - score,
  - supporting edges.
- Do not mutate the input `Evidence` raw fields during analysis.
- Add or update tests so these contracts are locked down.

## Acceptance Criteria

- [x] Pipeline result serialization includes linked entities, consistency score,
  inconsistent fields, correction candidates, top-k paths, and human feedback.
- [x] Tests assert correction candidate IDs and path IDs are stable for a known
  example.
- [x] Tests assert source edges include `edge_id`, `source`, `evidence`,
  `confidence`, `weight`, `review_status`, and feedback counters.
- [x] Tests assert the original evidence object is not mutated by
  `KGTracePipeline.analyze()`.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run python scripts/run_examples.py` passes.

## Out Of Scope

- No metrics implementation in this task.
- No noise injection implementation in this task.
- No Streamlit UI changes unless a tiny compatibility adjustment is required.
- No Neo4j behavior changes.
- No KG fact additions.

## Technical Notes

- Relevant files expected to be inspected by the implementation agent:
  - `src/kgtracevis/core/pipeline.py`
  - `src/kgtracevis/core/result.py`
  - `src/kgtracevis/kg/entity_linker.py`
  - `src/kgtracevis/kg/correction_generator.py`
  - `src/kgtracevis/kg/path_ranker.py`
  - `tests/test_pipeline.py`
  - `tests/test_path_ranker.py`
- This task follows from the roadmap in
  `.trellis/tasks/05-01-trellis-init-development-roadmap/prd.md`.
