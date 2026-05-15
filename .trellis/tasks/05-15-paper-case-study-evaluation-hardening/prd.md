# brainstorm: paper-facing case study evaluation hardening

## Goal

Iteratively harden the RootLens/KGTraceVis case-study evaluation path so Chapter 6 can use local, reproducible, quantitatively credible results rather than placeholders.

## What I Already Know

* The user wants code changes, repeated local runs, and debugging until the results are credible enough to give GPT Pro concrete values and artifacts for case-study writing.
* The paper needs Section 6 results for TEP, wafer, MVTec, and expert feedback.
* TEP is the primary quantitative RCA case.
* MVTec and WM811K/wafer must keep candidate/plausible claim boundaries unless reviewed process RCA references exist.
* Current implementation has `scripts/evaluate_tep_rca.py`, `run_adapter_pipeline.py`, `run_experiment_suite.py`, `build_paper_tables.py`, metrics helpers, and paper-facing docs.
* Workflow guidelines require reusable logic under `src/kgtracevis/`; scripts should only parse args and call workflows.

## Assumptions

* First milestone should focus on deterministic local artifacts under `runs/paper_case_studies/`.
* We should not invent or cherry-pick results. Quantitative tables must come from fixed commands and include case counts and claim boundaries.
* It is acceptable to add summary/export helpers if current artifacts are insufficient for paper tables.

## Requirements

* Run current TEP, MVTec, and wafer evaluation commands and inspect outputs.
* Identify failure modes or questionable metrics before changing code.
* Improve reusable workflows/scripts only where needed to make artifacts clearer, reproducible, or more paper-facing.
* Preserve adapter and RCA boundaries.
* Produce a concise local result summary for GPT Pro after verification.

## Acceptance Criteria

* [ ] TEP evaluation command runs locally and produces summary/table artifacts.
* [ ] MVTec and wafer adapter-to-pipeline commands run locally and produce scoped summaries/tables.
* [ ] Results include metric scope and claim boundary.
* [ ] Any code changes have focused tests or existing tests covering the behavior.
* [ ] Final output lists exact commands, artifact paths, and paper-usable values.

## Definition of Done

* Commands run successfully or blockers are documented with concrete errors.
* Changed Python code passes targeted tests.
* `uv run python scripts/run_examples.py` passes if core pipeline behavior is changed.
* No unsupported industrial facts or reviewed KG overwrites are introduced.

## Out of Scope

* Fabricating performance numbers.
* Running external web research.
* Building a formal expert user study.
* Promoting generated `runs/` outputs into tracked paper assets without user review.

## Technical Notes

Relevant specs read:

* `.trellis/spec/backend/workflow-architecture.md`
* `.trellis/spec/backend/adapter-guidelines.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/quality-guidelines.md`
* `.trellis/spec/backend/error-handling.md`
* `.trellis/spec/guides/index.md`
