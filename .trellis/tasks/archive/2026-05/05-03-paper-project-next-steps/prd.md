# brainstorm: paper project next steps

## Goal

Decide the next development direction for KGTraceVis as a paper project after
the 2026-05-02 demo milestone, with a bias toward work that advances paper
credibility and reproducibility while postponing tasks that require substantial
manual operation.

## What I Already Know

- The repository has a working v0 pipeline: schema validation, entity linking,
  consistency checking, correction generation, path ranking, scripts, metrics,
  and Streamlit demo.
- The project intentionally positions KGTraceVis as a knowledge-enhanced
  evidence analysis and traceability pipeline, not a new anomaly detector.
- MVTec / DS-MVTec must not be described as having verified factory RCA labels.
- TEP still needs to be implemented as a supported scenario, but it is not the
  current priority.
- The current responsible datasets are WM811K / wafer maps and MVTec.
- WM811K is best treated as wafer map spatial pattern recognition plus
  traceability/evidence-consistency analysis unless private process logs or
  reviewed RCA labels become available.
- Existing docs already separate observed evidence, KG source edges, and
  evaluation references.
- Baseline verification on 2026-05-03:
  - `uv run --extra dev pytest -q`: 84 passed.
  - `uv run python scripts/run_experiment_suite.py`: 6 commands passed.

## Assumptions

- The immediate goal is not another meeting-only demo, but progress toward a
  defensible paper prototype.
- Work that depends on large manual review, expert annotation, or human-study
  logistics should be delayed.
- Small, high-value manual curation is acceptable when it unlocks a clear
  experiment table or case study.
- Existing v0 scripts and Streamlit should be extended, not replaced.
- Because TEP is not the current focus, near-term paper readiness should come
  from WM811K/MVTec evidence quality, noise robustness, correction, provenance,
  and carefully bounded plausible explanation rather than strong verified RCA
  accuracy.

## Requirements

- Identify the next work package that most improves paper readiness.
- Preserve the source-constrained KG boundary and avoid unsupported industrial
  causal claims.
- Formalize adapter work as a two-layer ingestion design:
  model-dependent producer first, model-independent Evidence adapter second.
- Prioritize adapter implementation and end-to-end pipeline execution before
  expanding manual KG/reference curation.
- Ensure each focused dataset can run through:
  `adapter -> Evidence JSON -> KGTracePipeline -> top-k paths -> candidate root
  cause / plausible explanation`.
- Prioritize reproducible scripts, reference eligibility rules, and paper-table
  outputs over manual UI polish after the adapter-first loop is stable.
- Make WM811K and MVTec the core datasets for the next phase.
- Use MVTec for visual defect evidence normalization, mask/caption-derived
  morphology/location, consistency/correction, and curated-plausible
  explanation.
- Use WM811K for wafer map spatial pattern evidence, location/morphology/severity
  extraction, class-imbalance-aware evaluation, and traceability/case-study
  reasoning.
- Treat RCA/path-ranking metrics as bounded auxiliary metrics unless reference
  rows are clearly marked as reviewed/literature-supported/plausible.
- Keep TEP in the roadmap as a later supported adapter/scenario, not as a
  blocker for the current WM811K/MVTec milestone.

## Recommended Direction

Use an adapter-first milestone, then build a paper-experiment protocol and
artifact layer over the working end-to-end outputs.

Immediate focus:

1. Implement/strengthen WM811K and MVTec Evidence adapter contracts while
   keeping optional model producers separate.
2. Ensure both focused datasets can produce top-k paths and candidate/plausible
   root causes through `KGTracePipeline`.
3. Define reference eligibility and metric-scope rules.
4. Turn schema/linking/consistency/correction/noise outputs into grouped
   paper-ready tables.
5. Keep path-ranking as curated-plausible explanation or case-study output, not
   the main quantitative claim.
6. Add ablations only after the grouped baseline is stable.
7. Keep Streamlit as a lightweight provenance/what-if demo.

## Acceptance Criteria

- [x] A document under `docs/` defines paper experiment protocol and reference
      eligibility.
- [x] `data/references/*.csv` usage is mapped to metric eligibility and paper
      wording.
- [x] WM811K/wafer-map records can produce stable evidence observations for
      spatial pattern, morphology, location, severity, and confidence.
- [x] MVTec records can produce stable evidence observations for defect type,
      morphology, location, severity, and confidence.
- [x] The focused datasets can run end to end and emit `top_k_paths` with stable
      path IDs, source edges, and candidate root-cause/plausible-explanation
      nodes.
- [x] Experiment outputs can be grouped by dataset, noise type, annotation type,
      and metric scope.
- [x] Selected paper tables/figures have command provenance.
- [x] MVTec and WM811K/wafer claims remain explicitly bounded.

## Definition of Done

- Tests pass after implementation work.
- `uv run python scripts/run_experiment_suite.py` passes.
- New paper-facing outputs are generated under `runs/`, `outputs/`, or
  `artifacts/`; only reviewed stable assets are copied into `paper/`.
- Documentation is updated when experiment scope or paper claims change.

## Out of Scope

- Large manual KG review.
- Large MVTec plausible RCA expansion.
- Large WM811K/wafer expert-label collection.
- TEP deep evaluation and TEP-focused paper tables for the current milestone.
- Human-feedback user study.
- Complex online learning from feedback.
- Neo4j performance evaluation.
- LLM/embedding fallback for entity linking.
- Custom frontend rewrite.
- New anomaly detector training.

## Research References

- `research/next-step-assessment.md` - local repo and baseline assessment for
  next-step prioritization.
- `research/adapter-options.md` - adapter implementation options for
  MVTec/DS-MVTec and WM811K.
- `info.md` - detailed adapter-first implementation route.
- `implementation-plan.md` - concrete file-level implementation sequence for
  the first adapter batch.

## Technical Notes

- Relevant docs inspected:
  - `README.md`
  - `docs/development_plan.md`
  - `docs/experiment_plan.md`
  - `docs/group_meeting_demo_notes.md`
  - `docs/kgtracevis_revised_research_plan_cn.md`
  - `docs/implementation_research_plan.md`
  - `docs/adapter_evidence_generation_plan_cn.md`
  - `docs/research_brief.md`
  - `paper_idea_cn_dynamic_draft.md`
- Relevant generated baseline files:
  - `runs/v0_experiment_suite/summary.json`
  - `runs/v0_experiment_suite/table_summary.csv`
  - `runs/v0_experiment_suite/kg_qa_report.json`
