# RootLens KG Management Studio Foundation

## Goal

Add a non-mutating KG management foundation to the RootLens dashboard so the
paper demo can show not only case reasoning, but also how source-grounded KG
rows are inspected, traced to sources, and reviewed before any promotion into
tracked KG files.

## What I Already Know

- The dashboard already supports upload, run history, run detail, path graph
  provenance, and stable review feedback.
- Candidate KG artifacts already exist locally under `runs/paper_case_kg/` and
  `runs/end_to_end_interpretability_audit/candidate_kg/`.
- Source metadata is tracked in `data/kg/source_registry.csv` and source notes
  live under `docs/sources/`.
- Project rules require every KG edge to carry source, evidence, confidence,
  weight, review status, and feedback counters.
- We should not mutate `data/kg/` from the dashboard foundation.

## Requirements

### Backend/API

1. Add reusable KG Studio payload construction under `src/kgtracevis/service/`
   or a nearby reusable module.
2. Add a read-only API endpoint, likely `GET /api/kg/studio`, that returns:
   - source registry rows;
   - available source documents;
   - selected candidate KG artifact directory;
   - candidate node/edge counts;
   - scenario counts;
   - review status counts;
   - confidence summary;
   - validation summary when available;
   - bounded graph preview nodes/edges;
   - stable edge review targets.
3. Prefer `runs/paper_case_kg/` when present, then fallback to
   `runs/end_to_end_interpretability_audit/candidate_kg/`.
4. Handle missing candidate artifacts gracefully with an empty payload.
5. Do not write KG CSV files or promote reviewed rows in this task.

### Frontend

1. Add a KG Studio section to the dashboard shell.
2. Show candidate KG overview metrics and validation status.
3. Show source registry rows and source document paths.
4. Show a bounded graph preview for candidate edges with source/evidence
   inspection.
5. Show KG edge review targets that can drive the existing feedback endpoint.
6. Keep the interface usable without a selected run.
7. Keep responsive layout and text wrapping robust.

### Feedback

1. Edge review submissions should reuse existing `/api/feedback`.
2. Feedback metadata should include the KG Studio source path/artifact context
   and stable `target_key`.
3. No feedback should mutate candidate or tracked KG CSVs yet.

### Documentation

1. Update `docs/rootlens_dashboard.md` with KG Studio scope and non-mutating
   boundary.
2. Update README only if launch/check commands change.

### Quality

1. Extend dashboard smoke to exercise `GET /api/kg/studio`.
2. Add or update tests if backend payload construction has non-trivial parsing.
3. Run Python and frontend quality gates.

## Out of Scope

- Full force-directed arbitrary KG editing.
- LLM source-to-KG generation UI.
- Promotion workflow into `data/kg/`.
- Authentication, roles, or multi-user review.
- Writing back accepted/rejected counters to KG CSV files.

## Acceptance Criteria

- [ ] Dashboard can display KG candidate summary without requiring a selected
  run.
- [ ] Candidate edges expose source/evidence/confidence/review status.
- [ ] Edge review targets have stable `target_key` values and can be submitted
  through existing feedback.
- [ ] Missing candidate KG artifacts produce an empty, non-crashing UI.
- [ ] Quality gates pass for touched layers.

