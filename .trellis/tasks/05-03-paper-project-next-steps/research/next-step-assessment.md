# Next-Step Assessment for KGTraceVis Paper Project

Date: 2026-05-03

## Question

What should the project do next to move from a working demo toward a defensible
paper prototype, while postponing work that especially requires manual
operation?

## Current Baseline

The repository already has a working v0 loop:

```text
example evidence -> schema validation -> entity linking -> consistency check
-> correction candidates -> path ranking -> Streamlit / scripts
```

Observed implementation coverage:

- Reusable pipeline exists in `src/kgtracevis/core/pipeline.py`.
- Schema, adapters, in-memory KG, KG construction helpers, noise injection,
  metrics, feedback records, service handlers, Streamlit app, scripts, and tests
  are present.
- Checked-in examples cover MVTec, TEP, wafer, and one noisy MVTec morphology
  case.
- `data/references/` exists and explicitly separates reference rows from
  adapter input / runtime `kg_analysis`.
- `docs/group_meeting_demo_notes.md` and
  `docs/kgtracevis_revised_research_plan_cn.md` already state the important
  research boundary: MVTec paths are curated plausible references, not verified
  factory RCA labels.

Baseline commands run during this assessment:

```bash
uv run --extra dev pytest -q
uv run python scripts/run_experiment_suite.py
```

Results:

- Tests: 84 passed.
- Experiment suite: 6 commands passed.
- Suite output: `runs/v0_experiment_suite/summary.json`.
- Table output: `runs/v0_experiment_suite/table_summary.csv`.

Experiment-suite summary:

- 4 example cases validate and run through the pipeline.
- KG build reports 36 nodes and 29 edges.
- KG QA has 0 issues and 8 warnings.
- Noise experiment generated 96 records.
- Path ranking wrote summaries for 4 cases.

KG QA warnings:

- 4 reviewed MVTec plausible edges have confidence below 0.7.
- 4 nodes are isolated in the raw CSV edge set.

These warnings do not block the demo, but they matter for paper claims because
they expose the difference between demo plausibility and paper-grade evidence.

## Scope Revision

User correction on 2026-05-03:

> TEP-related adapter work is not owned by this project track. The current focus
> should be WM811K and MVTec.

This changes the earlier recommendation. TEP should no longer be the immediate
main quantitative path. It can remain in the repository as a compatibility/demo
scenario, but the next paper-facing plan should not depend on new TEP adapter or
TEP reference work.

Second user clarification on 2026-05-03:

> TEP still needs to be implemented, but it is not the current focus. The
> immediate need is to implement the corresponding adapters, run the whole flow,
> and generate top-k paths and root causes.

Updated interpretation:

- TEP stays on the roadmap as a supported adapter/scenario.
- The current milestone should not wait for TEP.
- The immediate engineering goal is adapter-first end-to-end execution for the
  focused datasets, especially WM811K and MVTec.
- "Root cause" outputs should be phrased as candidate root causes or plausible
  explanations unless the dataset/reference row provides verified support.

The responsible data track is now:

- MVTec / DS-MVTec: visual defect evidence, mask/caption-derived
  anomaly_type/location/morphology/severity, consistency/correction, and
  curated-plausible explanation.
- WM811K / wafer maps: spatial pattern recognition, wafer map morphology,
  location/zone/severity extraction, class-imbalance-aware evaluation, and
  source-bounded traceability/case-study explanation.

Important boundary:

- Public WM811K supports wafer map spatial pattern classification much better
  than verified process RCA.
- Without private process logs, lot/tool/chamber records, or reviewed expert
  labels, WM811K should not carry strong process-root-cause accuracy claims.
- If synthetic/demo logs are used, they must be marked `demo_synthetic` and kept
  out of primary ground-truth metrics.

## Main Diagnosis

The next bottleneck is no longer "make the system run." The system runs.

The next bottleneck is "make the WM811K/MVTec adapter-to-path loop real, then
make those outputs defensible as paper artifacts":

1. Implement/strengthen adapters so raw records or detector outputs become
   stable evidence observations.
2. Ensure each focused dataset can run through the same runtime pipeline and
   produce `top_k_paths` plus candidate root-cause/plausible-explanation nodes.
3. Define which references are eligible for which metrics.
4. Expand WM811K/MVTec evidence records without requiring heavy manual review.
5. Turn the existing v0 experiment outputs into repeatable tables / figures.
6. Keep all claims aligned with source-constrained KG and dataset limitations.

Human-heavy work should be delayed:

- large manual KG review,
- large MVTec plausible RCA curation,
- wafer/WM811K expert validation,
- full human-in-the-loop feedback study,
- polishing a large UI beyond what is needed to show provenance and what-if.

## Recommended Next Step

Recommended immediate task:

> Implement the WM811K/MVTec adapter-first end-to-end loop, then build a
> paper-experiment protocol and artifact layer over the generated top-k paths,
> candidate root causes, deterministic noise/correction outputs, and provenance.

This is better than starting with manual KG expansion because it uses the
existing working system and mostly requires scripts, configs, reference
contracts, table generation, and documentation.

## Proposed Work Packages

### WP1: Adapter-First End-to-End Loop

Goal: make the focused datasets actually enter the system through adapters and
leave the system with runtime top-k paths and candidate root causes.

Deliverables:

- WM811K/wafer-map adapter contract:
  - spatial pattern,
  - wafer zone/location,
  - morphology,
  - severity,
  - confidence,
  - optional descriptor/saliency provenance.
- MVTec/DS-MVTec adapter contract:
  - object,
  - defect/anomaly type,
  - mask/caption-derived morphology,
  - location,
  - severity,
  - confidence,
  - detector/caption/mask provenance.
- End-to-end scripts or examples showing:
  - adapter input record,
  - validated `Evidence`,
  - `KGTracePipeline.analyze(...)`,
  - `top_k_paths`,
  - candidate root-cause/plausible-explanation node,
  - source edge provenance.

Why now:

- Without adapter-first execution, paper tables risk evaluating hand-written
  examples rather than the intended system.
- It proves the core claim that heterogeneous anomaly outputs can be normalized
  and passed through one KG reasoning pipeline.
- It avoids heavy manual work while still producing visible progress.

### WP2: Paper Experiment Contract

Goal: define what each metric is allowed to mean.

Deliverables:

- A concise experiment protocol document under `docs/`.
- A reference eligibility contract for `data/references/*.csv`.
- Clear labels for metric scopes:
  - `native_ground_truth`
  - `official_fault_type`
  - `literature_supported`
  - `manual_plausible`
  - `demo_synthetic`
- A rule that primary quantitative tables should prioritize evidence-facing
  tasks for WM811K/MVTec: schema validity, linking, consistency, correction,
  noise recovery, and pattern/defect classification evidence quality.
- A rule that MVTec/WM811K RCA/path-ranking rows must be titled as
  "curated plausible references" or "case-study explanation" unless verified
  process RCA labels become available.

Why now:

- Prevents accidental overclaiming.
- Converts the existing v0 metrics into paper-safe language.
- Requires little manual industrial annotation.

### WP3: WM811K + MVTec Evidence Quantitative Track

Goal: make WM811K and MVTec the first defensible quantitative evidence-analysis
track.

Deliverables:

- Implement or strengthen WM811K evidence generation from wafer map records:
  spatial pattern, location/zone, morphology, severity, confidence, and optional
  saliency/descriptor provenance.
- Strengthen MVTec evidence generation from detector/DS-MVTec-style records:
  defect type, mask/caption-derived morphology, location, severity, confidence,
  and provenance.
- Add grouped metrics for schema validity, entity linking, consistency
  detection, correction, and noise recovery by dataset and noise type.
- Keep path-ranking metrics secondary and scope-labeled when using plausible
  references.

Why now:

- WM811K and MVTec are the datasets actually owned by this track.
- Both can support reproducible, low-manual evidence/correction experiments.
- This avoids depending on a TEP adapter owned elsewhere.

### WP4: Deterministic Noise and Correction Tables

Goal: produce repeatable results for consistency checking and correction.

Deliverables:

- Per-dataset/per-noise-type metric tables.
- Clean vs noisy comparisons.
- Optional ablations:
  - without KG consistency constraints,
  - without correction step,
  - mask/geometry-only vs caption/semantic-only evidence where available,
  - reviewed-only KG vs reviewed+auto KG,
  - optional shortest path only vs relation-weighted ranking for
    plausible-reference paths.

Why now:

- Existing `run_noise_experiment.py` already works.
- The current aggregate metrics are demo-scale; they need table shaping and
  clearer grouping before they become paper material.

### WP5: Paper Artifact Export

Goal: make selected outputs reproducible and citeable in the paper draft.

Deliverables:

- A generated table summary under `runs/`, then reviewed/stable copies under
  `paper/tables/` when ready.
- A command provenance note for each selected table/figure.
- At least one architecture/reasoning-flow figure generated from a documented
  source.

Why now:

- Converts working code into paper assets.
- Minimizes manual UI work.

### WP6: Minimal Demo Hardening

Goal: keep the Streamlit demo useful without turning it into a big product.

Deliverables:

- Ensure the app can load the experiment/path-ranking summaries.
- Ensure source edge provenance remains visible.
- Keep what-if editing and feedback hooks lightweight.

Why later than experiment protocol:

- The demo already works.
- Paper credibility currently depends more on experiment boundaries than UI
  polish.

## Work to Defer

Defer because it requires heavy manual operation:

- Large manual review of all KG edges.
- Large MVTec object/defect/plausible RCA expansion.
- WM811K/wafer expert-label collection and large-scale RCA accuracy claims.
- Manual human-feedback user study.
- Complex confidence learning from feedback.
- Large Neo4j performance evaluation.
- TEP-focused paper tables and deep evaluation for the current milestone.

Defer because it is technically tempting but not central:

- LLM/embedding entity-linking fallback.
- Large-scale LLM KG extraction benchmark.
- Custom frontend rewrite.
- New anomaly detector training.

## Suggested Order

1. Build/strengthen WM811K and MVTec adapters.
2. Run adapter outputs through the full pipeline and verify `top_k_paths` plus
   candidate root-cause/plausible-explanation outputs.
3. Write the paper experiment protocol and reference eligibility contract.
4. Build/strengthen WM811K and MVTec evidence generation and reference
   eligibility.
5. Add dataset/noise/annotation grouped metrics and paper-table export.
6. Add evidence/correction ablations.
7. Generate paper tables and a method figure with provenance notes.
8. Implement or deepen TEP when the WM811K/MVTec loop is stable.
9. Only then expand MVTec/WM811K plausible references manually if the paper
   narrative needs it.

## Success Criteria

- The experiment suite can produce grouped, paper-readable tables.
- WM811K/MVTec adapter records can run end to end without hand-filling
  `kg_analysis`.
- Runtime outputs include stable top-k path IDs, source edges, and candidate
  root-cause/plausible-explanation nodes.
- Every table states whether it is ground-truth, literature-supported, or
  curated-plausible.
- WM811K and MVTec have enough cases to carry the main evidence/correction
  quantitative claim.
- MVTec is framed as evidence normalization / consistency / plausible
  explanation, not true factory RCA.
- WM811K/wafer remains spatial-pattern/evidence traceability plus case-study
  explanation unless reliable process RCA labels are available.
- Manual annotation is limited to small, high-value reference rows.

## Updated Judgment

The paper should stop trying to make verified "root-cause path ranking accuracy"
the main quantitative spine for the immediate WM811K/MVTec track. TEP remains a
future supported scenario, but public WM811K/MVTec lack verified process RCA
labels. The stronger and safer near-term spine is:

```text
heterogeneous visual/wafer anomaly outputs
-> unified evidence observations
-> source-constrained KG linking
-> consistency checking under noisy fields
-> correction candidate generation
-> top-k candidate paths with provenance
-> candidate root cause / plausible explanation / case study
```

This still supports the KGTraceVis thesis, but the claim shifts from "we recover
true industrial root causes" to "we make anomaly evidence auditable, correctable,
and traceable under source constraints." TEP can later strengthen the RCA-facing
part once its adapter and references are ready.
