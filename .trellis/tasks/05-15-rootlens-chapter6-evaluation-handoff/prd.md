# brainstorm: RootLens chapter 6 case study handoff

## Goal

Create a paste-ready handoff document for WebGPT Pro to draft and refine Chapter 6, `Case Studies and Evaluation`, of the RootLens ChinaVis 2026 paper.

## What I Already Know

* The target section is `\section{Case Studies and Evaluation}` with four subsections: TEP RCA, Wafer Defect Traceability, Visual Evidence and KG Completion, and Expert Feedback.
* TEP is the main quantitative RCA case.
* MVTec-style data should be framed as visual evidence normalization / KG completion / weak RCA, not verified factory root cause analysis.
* WM811K/wafer should be framed as spatial-pattern evidence and candidate traceability unless backed by reviewed process references.
* The repository has a paper-facing experiment protocol and scripts for TEP RCA evaluation, adapter pipeline runs, noise experiments, path ranking, KG QA, and paper table manifests.
* Current paper-facing artifacts must explicitly name metric scope and claim boundary.

## Assumptions

* The deliverable is a Markdown handoff under `docs/`, not direct LaTeX edits.
* WebGPT Pro should draft cautiously and mark missing experiment values as `[VERIFY]`.
* Case-study writing should be VIS-style: workflow, observations, evidence/path review, quantitative metrics where valid, and limitations.

## Requirements

* Provide task instructions, expected output, writing constraints, and current chapter skeleton.
* Give case-by-case writing guidance and claim boundaries.
* Map each case to current commands/artifacts and paper-safe metrics.
* Distinguish quantitative evaluation, auxiliary/historical evidence, plausible-reference case study, and expert/formative feedback.
* Include safe and unsafe wording.

## Acceptance Criteria

* [ ] Handoff document exists under `docs/`.
* [ ] Handoff names current scripts/artifacts and evaluation commands.
* [ ] Handoff includes case-specific claim boundaries for TEP, wafer, MVTec, and expert feedback.
* [ ] Handoff tells WebGPT Pro not to invent numbers or expert-study details.

## Out of Scope

* Running experiments.
* Editing `paper/sections/06-case-studies-and-evaluation.tex`.
* Verifying final performance numbers.
* Creating figures or tables.

## Technical Notes

Inspected:

* `docs/paper_experiment_protocol.md`
* `scripts/evaluate_tep_rca.py`
* `src/kgtracevis/workflows/tep_evaluation.py`
* `src/kgtracevis/experiments/adapter_pipeline.py`
* `src/kgtracevis/experiments/paper_tables.py`
* `src/kgtracevis/metrics/*`
* `docs/rootlens_dashboard.md`
* `data/references/*`
