# implement: coverage-first KG hardening pipeline

## Goal

Implement a coverage-first, source-constrained KG hardening pipeline for MVTec
and WM811K paper artifacts. The pipeline should generate candidate KG CSVs,
case audit tables, validation reports, and before/after reasoning summaries
without claiming verified RCA.

## Requirements

* Audit existing MVTec calibrated records and WM811K records/adapter outputs.
* Generate coverage-oriented case ranking artifacts under `runs/`.
* Build candidate KG nodes/edges for MVTec visual defects and the eight public
  WM811K defect patterns.
* Keep candidate KG output under `runs/` by default.
* Preserve source, evidence, confidence, weight, review status, and feedback
  counters on every edge.
* Add adapter-pipeline support for overlay KG node/edge paths.
* Produce before/after comparison artifacts for base KG vs candidate overlay.
* Add tests for ranking, KG generation/validation, overlay loading, and WM811K
  `Loc` path isolation.

## Acceptance Criteria

* [ ] `scripts/audit_case_explainability.py` writes MVTec and WM811K ranking
      CSV/JSON/Markdown artifacts.
* [ ] `scripts/build_case_kg.py` writes candidate KG CSVs plus summary,
      validation, before/after, and top explanation artifacts.
* [ ] Candidate KG includes the eight WM811K pattern nodes and prevents `Loc`
      from routing through `NearfullDefect`.
* [ ] Candidate KG loads through `KnowledgeGraph.from_paths()`.
* [ ] Tests cover the new behavior.
* [ ] Quality gates are run and reported.

## Out of Scope

* Promoting generated candidate rows into tracked `data/kg/*.csv`.
* Claiming verified MVTec factory root causes.
* Adding Neo4j-specific behavior.
* Downloading or committing large datasets/checkpoints.

## Technical Notes

* Use existing `KGNode`, `KGEdge`, CSV export, QA, and `KGTracePipeline` helpers.
* Keep scripts thin; reusable logic belongs in `src/kgtracevis/kg_construction/`.
* Explanation scope remains candidate/plausible RCA only.
