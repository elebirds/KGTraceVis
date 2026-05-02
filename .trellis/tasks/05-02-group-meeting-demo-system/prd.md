# brainstorm: group meeting demo system

## Goal

Deliver a stable, end-to-end KGTraceVis demo system for the 2026-05-02 10:00 group meeting. The demo may use manually curated sample datasets and KG files, but the pipeline should feel complete: example evidence enters the system, KG reasoning analyzes it, the interface shows intermediate and final outputs, and reproducibility commands can be run live or cited in slides.

## What I Already Know

* The user wants a system-level report/demo by tomorrow morning.
* The group meeting is on 2026-05-02 at 10:00.
* The preferred demo mode is a live Streamlit demonstration.
* Dataset samples and KG facts may be hand-built examples for this milestone.
* The important goal is pipeline completeness rather than formal dataset/KG coverage.
* The intended research system is human-in-the-loop: evidence review, KG linking, consistency checking, correction review, ranked RCA paths, and feedback-compatible outputs.
* Existing repo already has a reusable `KGTracePipeline`, evidence schema, adapters, in-memory KG loader, KG construction helpers, QA, noise injection, metrics, scripts, tests, and Streamlit demo.
* Current smoke checks pass: `uv run --extra dev pytest -q` reports 63 passed, and `uv run python scripts/run_examples.py` analyzes MVTec, TEP, and wafer examples.
* Current checked-in KG is small: 36 nodes and 29 edges in QA output, enough for a demo but not paper-grade.

## Assumptions

* The group meeting demo should prioritize a reliable local Streamlit walkthrough plus command-line reproducibility as backup.
* It is acceptable to use curated toy examples if the presentation clearly labels them as manually constructed v0 demonstration data.
* We should avoid major new dependencies or architectural rewrites before the meeting.
* We should not claim MVTec has verified factory root causes.

## Requirements

* Provide a crisp demo narrative that maps directly to the paper idea: data/evidence -> KG -> adapter JSON -> RCA analysis -> human review.
* Optimize the first-run experience for Streamlit live demonstration.
* Ensure at least three scenarios can be demonstrated: MVTec-style visual defect, TEP process fault, and wafer image/log case.
* Ensure the UI exposes raw evidence, normalized evidence, linked entities, consistency score, inconsistent fields, correction candidates, top-k paths, and provenance/source edges.
* Ensure scripts can produce reproducible outputs for examples, KG QA, path ranking, and a small noise/metric experiment.
* Ensure generated demo outputs clearly distinguish v0 demonstration results from formal paper-grade experiments.
* Keep all core logic inside `src/kgtracevis/`; scripts and Streamlit remain clients.

## Acceptance Criteria

* [ ] A user can run the Streamlit demo and walk through all three example cases.
* [ ] At least one case shows a meaningful inconsistency/correction story, not only all-green examples.
* [ ] Top-k RCA paths include stable path IDs and source edge provenance.
* [ ] CLI commands for examples, KG QA, path ranking, and experiment suite are documented or easy to run.
* [ ] Tests, lint/type checks, and example runs pass or any exceptions are explicitly documented.
* [ ] Demo scope is documented as manually curated v0 sample data and KG, not final paper data.

## Definition of Done

* Tests added/updated where behavior changes.
* `uv run --extra dev pytest`, `uv run --extra dev ruff check .`, `uv run --extra dev mypy src tests scripts`, and `uv run python scripts/run_examples.py` have been attempted.
* Demo instructions and limitations are captured in docs or README-level notes.
* No unsupported industrial facts are added without source/evidence/confidence/review_status.

## Out of Scope

* Formal large-scale dataset annotation.
* Full paper-grade KG construction.
* Complex online learning from feedback.
* New front-end framework beyond the existing Streamlit demo.
* Claiming true factory RCA for MVTec examples.

## Technical Notes

* Existing backend spec index: `.trellis/spec/backend/index.md`.
* Relevant design docs already exist: `docs/development_plan.md`, `docs/experiment_plan.md`, `docs/implementation_research_plan.md`, `docs/project_design.md`.
* Existing app entry point: `src/kgtracevis/app/streamlit_app.py`.
* Existing reusable pipeline: `src/kgtracevis/core/pipeline.py`.
* Existing data examples: `data/examples/*.json`.
* Existing KG examples: `data/kg/*.csv`.
