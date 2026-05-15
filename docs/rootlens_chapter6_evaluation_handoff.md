# Handoff for WebGPT Pro: Case Studies and Evaluation Writing for RootLens

This handoff is meant to be pasted into WebGPT Pro to help draft and refine
Chapter 6, `Case Studies and Evaluation`, of the RootLens ChinaVis 2026 paper.
It summarizes the current KGTraceVis evaluation surface, case boundaries,
commands, artifact types, metric scopes, and claim limits.

## Task for WebGPT Pro

Help write `sections/06-case-studies-and-evaluation.tex` for the paper below.

Expected output:

1. A reviewer-facing evaluation narrative for Section 6.
2. A LaTeX draft for:

   ```latex
   \section{Case Studies and Evaluation}
   \label{sec:evaluation}
   ```

   with four subsections:

   ```latex
   \subsection{Case 1: Tennessee Eastman Process RCA}
   \subsection{Case 2: Wafer Defect Traceability}
   \subsection{Case 3: Visual Evidence and KG Completion}
   \subsection{Expert Feedback}
   ```

3. Suggested tables/figures for the evaluation section.
4. A list of values, experiment settings, and expert-study details that must be
   verified before final submission.

Important constraints:

- Write in academic English, suitable for a ChinaVis/VGTC-style visual
  analytics system paper.
- Do not invent performance numbers, participant counts, expert quotes, runtime
  values, baselines, ablation results, or statistical findings.
- Use `[VERIFY]` for missing values, counts, or metrics.
- Frame the evaluation as evidence-centered visual analytics plus
  source-grounded RCA, not as a new anomaly detector benchmark.
- Keep TEP as the main quantitative RCA case.
- Keep MVTec and WM811K/wafer claims conservative unless reviewed RCA
  references are available.
- Do not treat curated plausible references as verified industrial ground
  truth.
- Do not imply that feedback automatically mutates the production KG.

## Paper Identity

Current title:

`RootLens: Visual Analytics for Multi-Source Industrial Anomaly Detection and Traceable Root-Cause Analysis`

System name:

`RootLens`

Repository / implementation name:

`KGTraceVis`

Venue / format:

- ChinaVis 2026 candidate full paper.
- VGTC/ChinaVis LaTeX template.
- Main file: `paper/main.tex`.
- Target chapter file: `sections/06-case-studies-and-evaluation.tex`.

## Overall Paper Context

The paper structure is:

```text
1 Introduction
2 Related Work
3 Domain Problem and Design Requirements
4 Evidence-Centered RCA Framework
5 Visual Analytics System
6 Case Studies and Evaluation
7 Discussion and Conclusion
```

Section 6 should demonstrate that the framework and visual system support the
workflow described earlier. It should not redefine the framework from Section 4
or re-describe interface components from Section 5 except as needed to explain
how cases were analyzed.

## Evaluation Role of Section 6

Section 6 should answer four questions:

1. Can RootLens run a quantitative RCA evaluation when reliable process-fault
   references exist?
2. Can the same evidence/path/provenance workflow organize image/log or
   wafer-style traceability evidence?
3. Can visual anomaly evidence be converted into KG-linkable evidence and
   plausible KG completion / explanation candidates without overclaiming RCA
   ground truth?
4. Do domain experts find the evidence schema, source traces, candidate paths,
   and review workflow useful compared with isolated detector outputs?

The section should make the evidence strength explicit:

```text
TEP          -> primary quantitative RCA evaluation
Wafer        -> auxiliary/historical traceability case; candidate/plausible unless remapped and reviewed
MVTec        -> visual evidence, KG completion, weak/plausible RCA; not verified factory RCA
Expert input -> formative expert feedback unless a formal user study is completed
```

## External Structure References

Use these only as organization and tone references, not technical evidence:

- **AttnAnalyzer**: useful rhythm for Task/Requirements -> Data/Model ->
  Visual Analytics Environment -> Case Study -> Expert Feedback.
- **Curio**: useful for Design Goals -> Dataflow Model -> Framework -> Usage
  Scenarios + Expert Feedback; helps frame evidence/provenance/feedback as a
  coherent workflow.
- **DPVis**: useful for connecting domain workflow, usage scenario, and user
  experience.
- **LargeNetVis**: useful for system-design plus usage-scenario plus feedback
  structure.

Do not cite these papers in Section 6 unless citation integration is requested.

## Current Section Skeleton

```latex
\section{Case Studies and Evaluation}
\label{sec:evaluation}

\subsection{Case 1: Tennessee Eastman Process RCA}
% TODO: Use this as the main quantitative case. Add baseline, split, fault types, evaluation protocol, top-k metric definition, failure cases, runtime setup, and ablation before making performance claims.

\subsection{Case 2: Wafer Defect Traceability}
% TODO: Present this as historical or auxiliary evidence for image, log, KG, and path-ranking feasibility. Avoid treating it as a full validation of the new RootLens framework unless the workflow has been remapped and evaluated.

\subsection{Case 3: Visual Evidence and KG Completion}
% TODO: Use MVTec-style data as visual evidence / KG completion / weak RCA. State clearly that anomaly labels are not root-cause ground truth.

\subsection{Expert Feedback}
% TODO: Summarize whether the evidence schema, source traces, candidate paths, and KG editing workflow support RCA review better than isolated detector outputs.
```

## Current Evaluation Pipeline

The current paper-facing pipeline evaluates:

```text
producer-output records
-> Evidence adapters
-> validated Evidence JSON
-> KGTracePipeline
-> linked entities
-> consistency score and inconsistent fields
-> correction candidates
-> top-k paths and ranked root-cause candidates
-> scoped JSON/CSV tables and visual review
```

Important boundary:

Adapters produce observed evidence only. They do not emit root causes, ranked
paths, or prefilled KG analysis. Runtime outputs are computed by
`KGTracePipeline`.

## Reference Eligibility Rules

Use references according to their source strength:

| Reference type | Eligible paper use | Not eligible for |
|---|---|---|
| `native_ground_truth` | Dataset-observed labels such as defect class or spatial pattern when defined by the dataset. | Process RCA unless the dataset supplies reviewed RCA. |
| `official_fault_type` | Fault/event labels for benchmarks that define process faults. | Treating visual anomaly classes as root causes. |
| `literature_supported` | Secondary evidence or bounded candidate explanations when source text is recorded. | Strong claims without traceable source and review status. |
| `manual_plausible` | Case-study explanation, plausible-reference path hit, and demo review. | Primary verified RCA accuracy. |
| `demo_synthetic` | Reproducibility smoke tests and UI/demo examples. | Paper ground-truth tables. |
| `llm_candidate` | Candidate extraction backlog after validation and review. | Any ground-truth metric before review. |

This distinction should be visible in the writing. Do not collapse `manual
plausible` into ground truth.

## Case 1: Tennessee Eastman Process RCA

### Role in the Paper

TEP should be the main quantitative RCA case. It is the strongest case for
reporting top-k RCA metrics because TEP fault types can be used as evaluation
references.

Safe positioning:

- TEP evaluates whether the unified Evidence-to-KGTracePipeline path can
  support process-fault RCA.
- Fault labels are used as evaluation references only.
- RCA scoring uses adapter evidence, variable contributions, dynamic features,
  and Root-KGD support assets.
- Fault labels/fault numbers must not be described as scoring inputs.
- The TEP Root-KGD reasoner returns the same output contract as other cases:
  `top_k_paths` and `ranked_root_causes`.

### Current Implementation Path

Current command:

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_raw_batch_eval_unified \
  --raw-data-dir data/raw/tep \
  --faults 1,2,6 \
  --overwrite
```

Configurable options include:

```text
--faults
--max-runs-per-fault
--max-cases
--window-size
--row-stride
--fault-free-max-rows
--top-variables
--n-components
--top-k
--kg-node-path
--kg-edge-path
--use-neo4j-runtime
```

Generated artifacts:

```text
runs/tep_raw_batch_eval_unified/tep_rca_evaluation_summary.json
runs/tep_raw_batch_eval_unified/tep_rca_evaluation_cases.csv
runs/tep_raw_batch_eval_unified/tep_records.jsonl
runs/tep_raw_batch_eval_unified/adapter_pipeline/adapter_pipeline_summary.json
```

Evaluation workflow:

```text
raw TEP CSV or existing TEP producer JSONL
-> TEP producer records
-> TEP Evidence adapter
-> KGTracePipeline
-> TEP Root-KGD RCA reasoner
-> ranked_root_causes and top_k_paths
-> top-k metrics against fault references
```

### Current Metrics

The TEP workflow currently computes:

```text
top1_root_cause_accuracy
top3_root_cause_accuracy
topK_root_cause_accuracy
MRR
path_hit_rate
case_count
```

Case table fields include:

```text
case_id
fault_number
expected_root_cause_id
top1_candidate_id
rank
hit_at_1
hit_at_3
hit_at_k
reciprocal_rank
path_hit_at_k
ranked_root_causes
top_k_paths
```

### What WebGPT Pro Should Write

Write this case as:

1. Dataset and task setup.
2. Evidence generation protocol.
3. RCA evaluation protocol.
4. Metrics: top-k accuracy, MRR, path hit rate.
5. Results table placeholder with `[VERIFY]`.
6. Failure-case discussion placeholder.
7. Runtime/configuration placeholder.
8. Optional ablation paragraph only if artifacts exist or are clearly marked
   `[VERIFY]`.

### Missing Items to Mark `[VERIFY]`

Do not invent:

- Exact number of evaluated cases.
- Exact train/test split or run split.
- Fault list beyond the command default unless verified.
- Final top-k accuracy / MRR / path hit values.
- Baselines and ablation numbers.
- Runtime or hardware.
- Failure mode counts.

### Recommended TEP Results Table

Possible columns:

```text
Setting
Faults
Cases
Top-1
Top-3
Top-K
MRR
Path Hit
Notes
```

All values should be `[VERIFY]` unless read from final generated artifacts.

### Claim Boundary

Use wording like:

> We use TEP as the primary quantitative RCA scenario because its process-fault
> labels provide evaluation references. These labels are withheld from scoring
> and used only to compute ranking metrics.

Avoid:

- "RootLens learns the true causal structure of TEP."
- "Fault labels are input causes."
- "RootLens achieves state-of-the-art RCA" unless baselines are verified.

## Case 2: Wafer Defect Traceability

### Role in the Paper

Wafer should be written as an auxiliary traceability case, not as the main
quantitative validation of the new RootLens framework unless the workflow has
been explicitly remapped and evaluated under RootLens.

There are two possible evidence sources:

1. Current KGTraceVis / WM811K path:
   wafer spatial-pattern evidence, zones, morphology, severity, classifier
   metadata, KG-linked candidate paths.
2. Historical prior thesis / project evidence:
   wafer wet-process particle defect traceability with wafer scan images,
   machine logs, ontology/KG, entity extraction, Neo4j, and path ranking.

Keep these separate. Historical results may motivate feasibility, but they
should not be presented as direct RootLens evaluation unless remapped.

### Current Implementation Path

Current command for WM811K-style records:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_v0/wm811k \
  --overwrite
```

Current paper-safe outputs:

```text
adapter_pipeline_summary.json
adapter_pipeline_table.csv
generated Evidence JSON files
linked entities
consistency score
correction candidates
top-k candidate/plausible paths
source edge provenance
```

Paper-safe metrics / observations:

- schema validity / adapter reproducibility over checked-in examples,
- wafer spatial pattern evidence,
- location/zone, morphology, severity, confidence,
- entity linking,
- consistency / correction,
- candidate path review,
- optional noise recovery if a noise experiment is run.

### Historical Wafer Support

If using prior thesis/project notes, use careful wording:

- Scenario: wafer wet-process particle defects.
- Data: 8 batches and 200 production wafer scan images plus machine logs
  `[VERIFY]`.
- Ingredients: DCGAN augmentation, ResNet classifier, spatial weighting, wafer
  process ontology, BERT-BiLSTM-CRF entity extraction, Neo4j KG, path-ranking
  traceability `[VERIFY]`.
- Reported classifier accuracy: 94.06% `[VERIFY]`.
- Reported comprehensive traceability rate on 104 defective wafers: above 90%
  `[VERIFY]`.

But clearly state:

> These historical results support the feasibility of image/log/KG traceability
> in a wafer scenario. They are not direct validation of the current RootLens
> implementation unless the cases are remapped into the RootLens evidence
> contract and re-evaluated.

### What WebGPT Pro Should Write

Write this case as a traceability walkthrough:

1. Wafer evidence and source materials.
2. Conversion to Evidence observations.
3. KG-linked path review and provenance.
4. What this demonstrates: image/spatial/log-style evidence can be organized
   into the RootLens review workflow.
5. Boundary: candidate/plausible explanation unless verified process RCA
   references are available.

Avoid reporting public WM811K spatial pattern labels as root-cause labels.

## Case 3: Visual Evidence and KG Completion

### Role in the Paper

MVTec / DS-MVTec should be written as a visual evidence and KG completion /
weak-RCA case. It demonstrates that RootLens can ingest visual anomaly outputs,
derive KG-linkable observations, expose source traces, and suggest candidate KG
relations or plausible explanation paths.

This is not a verified factory RCA benchmark.

Safe positioning:

- MVTec-style data supports evidence normalization and visual anomaly review.
- Detector outputs include anomaly score, heatmap, mask, bbox, area ratio,
  morphology, location, severity, and confidence.
- Native defect labels may be dataset/operator labels, not root causes.
- Candidate paths are plausible explanation paths or KG completion candidates,
  not verified root causes.

### Current Implementation Path

Current command:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/mvtec_records.jsonl \
  --dataset mvtec \
  --output-dir outputs/adapter_pipeline_v0/mvtec \
  --overwrite
```

Related examples:

```text
data/examples/ds_mvtec_example.json
data/examples/mvtec_noisy_morphology_demo.json
data/examples/records/mvtec_records.jsonl
```

Current paper-safe outputs:

```text
generated Evidence JSON
linked entities
consistency score
inconsistent fields
correction candidates
top-k candidate/plausible paths
source edge provenance
visual evidence previews in the dashboard
```

Current paper-safe metric areas:

- schema validity,
- entity linking,
- morphology/location consistency,
- correction candidate generation,
- controlled noise recovery,
- path hit against curated plausible references if a reference table is used.

### MVTec Reference Boundary

Use:

```text
data/references/mvtec_plausible_rca_reference.csv
```

only as:

> curated plausible visual explanation references

not as:

> verified factory root-cause ground truth.

### What WebGPT Pro Should Write

Write this case as:

1. Visual evidence ingestion.
2. Evidence normalization: object, visual anomaly label/prior, location,
   morphology, severity, heatmap/mask geometry.
3. KG linking and consistency/correction example.
4. KG completion or plausible path review.
5. Boundary: MVTec does not provide production RCA ground truth.

Do not write:

- "MVTec validates RCA accuracy."
- "PatchCore predicts root cause."
- "Defect type equals root cause."

## Expert Feedback

### Role in the Paper

This subsection should summarize formative expert feedback unless a formal
controlled user study has been completed.

Use this section to assess whether experts found these aspects useful:

- unified evidence schema,
- raw/source trace preservation,
- linked KG entities,
- consistency score and inconsistent fields,
- correction candidates,
- candidate root-cause paths,
- source edge provenance,
- KG review / draft adjustment workflow,
- feedback targets for paths, edges, entity links, and corrections.

### Current System Support

Current RootLens dashboard / service exposes:

```text
evidence summary
visual evidence previews
linked entities
consistency/correction outputs
top-k paths
derived path graph
source edge provenance
review targets
append-only feedback records
KG Studio source registry / candidate graph / review queue / draft adjustments
```

Feedback does not directly promote or mutate KG edges in the current
foundation version. It remains append-only review state.

### What WebGPT Pro Should Write

If expert feedback exists, write:

1. Participants and expertise `[VERIFY]`.
2. Procedure `[VERIFY]`: scenarios shown, tasks, duration, data used.
3. Feedback themes:
   - evidence unification helped compare model outputs,
   - source traces made candidate paths more trustworthy/reviewable,
   - candidate paths were useful as hypotheses, not final answers,
   - experts wanted clearer uncertainty/source quality cues,
   - KG editing/review should remain controlled.
4. Limitations: formative feedback, small participant count, not a controlled
   user study unless verified.

If expert feedback does not yet exist, draft as a planned/formative evaluation
template and mark details `[VERIFY]`.

### Safe Wording

Use:

- "formative expert feedback"
- "experts commented that..."
- "participants suggested..."
- "the feedback indicates potential usefulness..."
- "further controlled studies are needed..."

Avoid:

- "user study proves..."
- "experts confirmed correctness of RCA..."
- "feedback validates all root causes..."

## Metrics Definitions

Use concise definitions when needed:

- `Top-k RCA accuracy`: fraction of cases where the expected root-cause
  candidate appears in the top-k ranked candidates.
- `MRR`: mean reciprocal rank of the expected root-cause candidate.
- `Path hit rate`: fraction of cases where any top-k path includes or targets
  the expected root-cause candidate.
- `Schema validity rate`: fraction of generated evidence records that validate
  against the unified schema.
- `Entity linking accuracy / top-k linking accuracy`: whether expected KG
  entities appear as selected or top-k link candidates.
- `Correction accuracy / top-k correction accuracy`: whether expected corrected
  values appear in generated correction candidates.
- `Noise recovery rate`: fraction of corrupted fields recovered under a
  controlled noise protocol.

Do not mix metric computation with visualization claims.

## Current Commands and Artifact Map

Use these commands as current implementation anchors:

### TEP RCA

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_raw_batch_eval_unified \
  --raw-data-dir data/raw/tep \
  --faults 1,2,6 \
  --overwrite
```

### MVTec adapter-to-pipeline

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/mvtec_records.jsonl \
  --dataset mvtec \
  --output-dir outputs/adapter_pipeline_v0/mvtec \
  --overwrite
```

### WM811K / wafer adapter-to-pipeline

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_v0/wm811k \
  --overwrite
```

### Consolidated suite and paper tables

```bash
uv run python scripts/run_experiment_suite.py
uv run python scripts/build_paper_tables.py --overwrite
```

### Noise and path ranking

```bash
uv run python scripts/run_noise_experiment.py
uv run python scripts/run_path_ranking.py --write-json
```

### KG QA

```bash
uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json
```

## Suggested Tables and Figures

### Table: Case Study Summary

Columns:

```text
Case
Data/source
Evaluation role
Evidence types
Reasoning mode
Metrics / observations
Claim boundary
```

Rows:

```text
TEP
Wafer
MVTec
Expert feedback
```

### Table: TEP Quantitative Results

Columns:

```text
Setting
Faults
Cases
Top-1
Top-3
Top-K
MRR
Path hit
Notes
```

Use `[VERIFY]` for values until final artifacts are inspected.

### Figure: TEP Evaluation Flow

Flow:

```text
TEP raw CSV
-> producer records
-> Evidence adapter
-> KGTracePipeline
-> Root-KGD RCA reasoner
-> ranked_root_causes / top_k_paths
-> metrics against fault references
```

### Figure: Case Workflow Snapshots

Could show one compact example per case:

```text
raw evidence
-> normalized observations
-> linked entities
-> candidate path
-> source edge provenance
-> feedback target
```

### Table: Expert Feedback Themes

Columns:

```text
Theme
Observed benefit
Expert concern
Design implication
```

Suggested themes:

```text
evidence unification
source traceability
candidate path review
uncertainty and confidence
KG correction workflow
```

## Claims to Avoid

Avoid:

- "RootLens solves industrial RCA."
- "RootLens discovers true causes across all scenarios."
- "MVTec validates root-cause analysis."
- "WM811K public labels are process root causes."
- "LLM-extracted triples are trusted industrial facts."
- "Expert feedback proves RCA correctness."
- "Feedback automatically updates the KG."
- "TEP results are state-of-the-art" unless baselines are verified.

Use:

- "primary quantitative RCA case"
- "candidate root-cause paths"
- "plausible explanation references"
- "source-grounded provenance"
- "formative expert feedback"
- "evaluation references"
- "not used as scoring input"
- "requires further validation"

## Recommended Section Narrative

The Section 6 opening should briefly state:

> We evaluate RootLens through three complementary cases and formative expert
> feedback. TEP provides the main quantitative RCA evaluation because it offers
> process-fault references. The wafer case examines traceability across
> spatial/log-style evidence and KG paths. The MVTec case studies visual
> evidence normalization and KG completion under weak RCA supervision. Expert
> feedback assesses whether source traces and reviewable candidate paths better
> support industrial RCA sensemaking than isolated detector outputs.

Then make the strength of evidence explicit:

> These cases are intentionally not treated as equally strong ground truth
> benchmarks. Instead, each case evaluates a different part of the RootLens
> claim: quantitative RCA where references exist, traceability feasibility
> where historical or reviewed process evidence is available, and visual
> evidence organization where verified RCA labels are absent.

## Current Source Materials Used for This Handoff

Repository docs and files:

- `docs/paper_experiment_protocol.md`
- `docs/rootlens_dashboard.md`
- `docs/evidence_schema.md`
- `docs/project_design.md`
- `src/kgtracevis/workflows/tep_evaluation.py`
- `scripts/evaluate_tep_rca.py`
- `src/kgtracevis/experiments/adapter_pipeline.py`
- `src/kgtracevis/experiments/paper_tables.py`
- `src/kgtracevis/metrics/*`
- `data/references/README.md`
- `data/references/mvtec_plausible_rca_reference.csv`
- `data/references/tep_rca_reference.csv`
- `data/references/wafer_plausible_reference.csv`
- `docs/rootlens_chapter4_framework_handoff.md`

## Final Instruction for WebGPT Pro

Please draft Section 6 now. Make it read like a VIS/ChinaVis case-study and
evaluation section, not like a script manual. Keep TEP as the main quantitative
case, keep wafer as auxiliary traceability support unless remapped evaluation is
verified, and keep MVTec as visual evidence / KG completion / weak-RCA support.
Do not invent numbers. Use `[VERIFY]` for all missing metrics, expert details,
runtime setup, baselines, and ablations.
