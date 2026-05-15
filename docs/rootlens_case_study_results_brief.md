# RootLens Case Study Results Brief for GPT Pro

This brief contains reproducible local results from KGTraceVis for drafting
Section 6, `Case Studies and Evaluation`, of the RootLens paper. Use it together
with `docs/rootlens_chapter6_evaluation_handoff.md`.

## Writing Position

Use these results to support a conservative evaluation narrative:

- TEP is the main quantitative RCA evaluation.
- Wafer and MVTec are evidence traceability and plausible-explanation cases,
  not verified process-RCA benchmarks.
- Fault labels/fault numbers in TEP are evaluation references only, not scoring
  inputs.
- RootLens outputs ranked hypotheses and source-grounded paths for review; do
  not describe them as causal proof.

## Code Changes Made for Evaluation Credibility

The TEP evaluation workflow now writes two additional audit signals:

1. `fault_coverage`: records requested faults, observed faults, cases per fault,
   and missing requested faults.
2. `explicit_fault_label_ablation`: reruns TEP RCA after removing explicit
   `fault_number` and `fault_id` fields from producer records, then reports
   whether the top-1 prediction remains stable.

Per-case CSV rows now include:

- `explicit_fault_label_ablation_top1_candidate_id`
- `explicit_fault_label_ablation_top1_stable`

This supports a paper claim that TEP fault identifiers are used as evaluation
references, while RCA ranking remains stable when explicit fault labels are
removed from the runtime evidence record.

The MVTec/WM811K paper case-study path now also has a bounded evaluation
summarizer:

- `scripts/evaluate_paper_case_studies.py`
- `src/kgtracevis/workflows/paper_case_studies.py`

It consumes generated record and adapter-summary artifacts, then writes:

- `mvtec_object_selection.csv`: object-level visual model behavior, KG coverage,
  explainable-path coverage, and a transparent object-selection score.
- `wm811k_pattern_traceability.csv`: WM811K pattern coverage, native-vs-predicted
  pattern agreement where available, and traceability path coverage.
- `wm811k_stratified_pattern_traceability.csv`: a native-label,
  pattern-stratified WM811K case-study layer covering the eight public WM811K
  pattern classes.
- `paper_case_study_evaluation_summary.json`: paper-facing rollup with explicit
  claim boundaries for MVTec and WM811K.

WM811K pattern agreement is scoped to records that contain both a native pattern
reference and a predicted pattern. Native-only and predicted-only rows contribute
to pattern coverage and traceability, but not to exact pattern accuracy.
The stratified WM811K layer is native-label sampling for pattern coverage and
traceability/path coverage; it is not a classifier-performance result.

## TEP Main Quantitative Case

### All-Fault Smoke Evaluation

Command:

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/paper_case_studies/tep_rca_all_faults_smoke \
  --raw-data-dir data/raw/tep \
  --faults 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21 \
  --max-runs-per-fault 1 \
  --top-k 5 \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/tep_rca_all_faults_smoke/tep_rca_evaluation_summary.json`
- `runs/paper_case_studies/tep_rca_all_faults_smoke/tep_rca_evaluation_cases.csv`
- `runs/paper_case_studies/tep_rca_all_faults_smoke/tep_records.jsonl`
- `runs/paper_case_studies/tep_rca_all_faults_smoke/adapter_pipeline/adapter_pipeline_summary.json`

Coverage:

- Requested faults: 1-21.
- Observed faults in the local raw TEP file: 1-20.
- Missing requested fault: 21.
- Case count: 20, one case per observed fault.

Metrics:

| Metric | Value |
|---|---:|
| Case count | 20 |
| Top-1 root-cause accuracy | 0.80 |
| Top-3 root-cause accuracy | 0.90 |
| Top-5 root-cause accuracy | 0.90 |
| MRR | 0.8417 |
| Path hit rate | 0.90 |
| Explicit fault-label ablation top-1 stability | 1.00 |

Label-ablation audit:

- Scope: remove explicit `fault_number` and `fault_id` before rerunning RCA.
- Audited cases: 20.
- Top-1 stability: 1.00.
- Changed case IDs: none.

Failure cases to discuss:

| Fault | Expected candidate | Top-1 candidate | Expected rank | Top-5 hit | Path hit |
|---:|---|---|---:|---|---|
| 10 | `faultanchor:stream_4_feed_temperature` | `faultanchor:stream_2_feed_temperature` | 3 | true | true |
| 15 | `faultanchor:separator_coolant_valve_stiction` | `faultanchor:stream_2_feed_temperature` | 2 | true | true |
| 18 | `faultanchor:condenser_heat_transfer` | `faultanchor:stream_2_feed_temperature` | not in top-5 | false | false |
| 20 | `Fault20` | `faultanchor:multi_valve_stiction` | not in top-5 | false | false |

Suggested interpretation:

- Faults 10 and 15 are near misses: the expected candidates appear in top-3 and
  their paths are retrieved, but a recurrent feed-temperature candidate ranks
  first.
- Fault 18 is a miss under the current Root-KGD assets/features.
- Fault 20 falls back to `Fault20` because no Root-KGD fault anchor was found
  for this fault in the current assets; treat it as an asset coverage limitation.

### Stable Subset Sanity Check

Command:

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/paper_case_studies/tep_rca_broad \
  --raw-data-dir data/raw/tep \
  --faults 1,2,3,4,5,6,7,8 \
  --max-runs-per-fault 2 \
  --top-k 5 \
  --overwrite
```

Coverage:

- Requested faults: 1-8.
- Observed faults: 1-8.
- Case count: 16, two cases per fault.
- Missing requested faults: none.

Metrics:

| Metric | Value |
|---|---:|
| Case count | 16 |
| Top-1 root-cause accuracy | 1.00 |
| Top-3 root-cause accuracy | 1.00 |
| Top-5 root-cause accuracy | 1.00 |
| MRR | 1.00 |
| Path hit rate | 1.00 |
| Explicit fault-label ablation top-1 stability | 1.00 |

Suggested use:

- Use this as a sanity check or supplementary result.
- Do not make the whole evaluation look perfect. The all-fault smoke result is
  more credible as the main reported quantitative result because it includes
  clear failure cases and asset-coverage boundaries.

## Wafer Traceability Case

### Fixture Traceability Smoke

Command:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir runs/paper_case_studies/wafer_traceability \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/wafer_traceability/adapter_pipeline_summary.json`
- `runs/paper_case_studies/wafer_traceability/adapter_pipeline_table.csv`

Cases:

| Case | Consistency | Linked entities | Paths | Ranked hypotheses | Top candidate | Score | Source |
|---|---:|---:|---:|---:|---|---:|---|
| `wm811k_fixture_clean_nearfull` | 1.0 | 4 | 5 | 5 | `GlueRemovalInsufficient` | 0.4965 | `wafer_thesis` |
| `wm811k_fixture_descriptor_fallback` | 1.0 | 4 | 5 | 5 | `GlueRemovalInsufficient` | 0.4965 | `wafer_thesis` |

Claim boundary:

The adapter summary explicitly marks these cases as
`candidate/plausible explanation only; not a verified root-cause label`.

Suggested interpretation:

- Use this case to show that wafer spatial-pattern evidence can be normalized,
  linked to KG entities, and connected to source-grounded candidate paths.
- Do not report RCA accuracy for wafer unless a reviewed process-level RCA
  reference is added.

### Real WM811K Smoke Traceability

Commands:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input runs/wm811k_real_recognition_smoke/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir runs/paper_case_studies/wm811k_traceability_real \
  --top-k 5 \
  --overwrite

uv run python scripts/evaluate_paper_case_studies.py \
  --output-dir runs/paper_case_studies/evaluation_hardening \
  --mvtec-records runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl \
  --mvtec-adapter-summary runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_summary.json \
  --mvtec-pipeline-summary runs/mvtec_calibrated_pipeline/mvtec_calibrated_pipeline_summary.json \
  --wm811k-records runs/wm811k_real_recognition_smoke/wm811k_records.jsonl \
  --wm811k-adapter-summary runs/paper_case_studies/wm811k_traceability_real/adapter_pipeline_summary.json \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/wm811k_traceability_real/adapter_pipeline_summary.json`
- `runs/paper_case_studies/wm811k_traceability_real/adapter_pipeline_table.csv`
- `runs/paper_case_studies/evaluation_hardening/wm811k_pattern_traceability.csv`
- `runs/paper_case_studies/evaluation_hardening/paper_case_study_evaluation_summary.json`

Metrics and coverage:

| Metric | Value |
|---|---:|
| WM811K real-smoke cases | 5 |
| Observed supported patterns | 1 / 8 |
| Observed pattern | `Loc` |
| Native-vs-predicted pattern agreement | 1.00 |
| Traceability path coverage | 1.00 |
| Mean classifier confidence for `Loc` | 0.6613 |
| Mean linked entities for `Loc` | 4.0 |

All five real-smoke rows link to wafer evidence and return candidate paths. The
top candidate is `ProcessNonuniformity` with source-grounded, low-confidence
wafer-process interpretation. This is a traceability result over a narrow local
sample, not dataset-level WM811K performance.

### Pattern-Stratified WM811K Traceability Layer

Commands:

```bash
uv run python scripts/build_wm811k_stratified_records.py \
  --input data/external/wm811k/test.pkl \
  --output-jsonl runs/paper_case_studies/wm811k_stratified/wm811k_stratified_records.jsonl \
  --records-per-pattern 1 \
  --seed 0 \
  --overwrite

uv run python scripts/run_adapter_pipeline.py \
  --input runs/paper_case_studies/wm811k_stratified/wm811k_stratified_records.jsonl \
  --dataset wafer \
  --output-dir runs/paper_case_studies/wm811k_stratified_traceability \
  --top-k 5 \
  --overwrite

uv run python scripts/evaluate_paper_case_studies.py \
  --output-dir runs/paper_case_studies/evaluation_hardening \
  --mvtec-records runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl \
  --mvtec-adapter-summary runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_summary.json \
  --mvtec-pipeline-summary runs/mvtec_calibrated_pipeline/mvtec_calibrated_pipeline_summary.json \
  --wm811k-records runs/wm811k_real_recognition_smoke/wm811k_records.jsonl \
  --wm811k-adapter-summary runs/paper_case_studies/wm811k_traceability_real/adapter_pipeline_summary.json \
  --wm811k-stratified-records runs/paper_case_studies/wm811k_stratified/wm811k_stratified_records.jsonl \
  --wm811k-stratified-adapter-summary runs/paper_case_studies/wm811k_stratified_traceability/adapter_pipeline_summary.json \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/wm811k_stratified/wm811k_stratified_records.jsonl`
- `runs/paper_case_studies/wm811k_stratified/wm811k_stratified_build_summary.json`
- `runs/paper_case_studies/wm811k_stratified_traceability/adapter_pipeline_summary.json`
- `runs/paper_case_studies/wm811k_stratified_traceability/adapter_pipeline_table.csv`
- `runs/paper_case_studies/evaluation_hardening/wm811k_stratified_pattern_traceability.csv`
- `runs/paper_case_studies/evaluation_hardening/paper_case_study_evaluation_summary.json`

Metrics and coverage:

| Metric | Value |
|---|---:|
| Stratified records | 8 |
| Supported patterns covered | 8 / 8 |
| Supported pattern coverage rate | 1.00 |
| Adapter cases | 8 |
| Mean linked entities per pattern | 4.0 |
| Mean consistency score | 0.925 |
| Traceability path coverage | 1.00 |
| Exact pattern accuracy | not reported |

Pattern rows:

| Pattern | Consistency | Linked entities | Path coverage | Top candidate |
|---|---:|---:|---:|---|
| `Center` | 1.0 | 4.0 | 1.0 | `ProcessInterruption` |
| `Donut` | 1.0 | 4.0 | 1.0 | `ProcessNonuniformity` |
| `Edge-Loc` | 1.0 | 4.0 | 1.0 | `ChamberContamination` |
| `Edge-Ring` | 1.0 | 4.0 | 1.0 | `EdgeProcessIssue` |
| `Loc` | 1.0 | 4.0 | 1.0 | `ProcessNonuniformity` |
| `Random` | 0.7 | 4.0 | 1.0 | `ParticleContamination` |
| `Scratch` | 0.7 | 4.0 | 1.0 | `HandlingScratch` |
| `Near-full` | 1.0 | 4.0 | 1.0 | `GlueRemovalInsufficient` |

Claim boundary:

This layer samples one native-labeled WM811K row per supported public pattern
from `data/external/wm811k/test.pkl`. It is valid for pattern coverage and
source-grounded traceability/path coverage. It does not evaluate classifier
accuracy and does not provide process RCA ground truth.

## MVTec Visual Evidence and KG Completion Case

### Fixture Visual Evidence Smoke

Command:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/mvtec_records.jsonl \
  --dataset mvtec \
  --output-dir runs/paper_case_studies/mvtec_visual_evidence \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/mvtec_visual_evidence/adapter_pipeline_summary.json`
- `runs/paper_case_studies/mvtec_visual_evidence/adapter_pipeline_table.csv`

Cases:

| Case | Consistency | Linked entities | Paths | Ranked hypotheses | Top candidate | Score | Source |
|---|---:|---:|---:|---:|---|---:|---|
| `mvtec_fixture_clean_scratch` | 1.0 | 4 | 3 | 3 | `MechanicalContact` | 0.48 | `manual_curation` |
| `mvtec_fixture_mask_fallback` | 1.0 | 4 | 3 | 3 | `MechanicalContact` | 0.48 | `manual_curation` |

Claim boundary:

The adapter summary explicitly marks these cases as
`candidate/plausible explanation only; not a verified root-cause label`.

Suggested interpretation:

- Use this case to demonstrate visual evidence normalization, source-edge
  inspection, and KG completion / explanation candidate generation.
- State clearly that MVTec anomaly classes are not real industrial root-cause
  ground truth.

### Multi-Object MVTec Object Selection

Command:

```bash
uv run python scripts/evaluate_paper_case_studies.py \
  --output-dir runs/paper_case_studies/evaluation_hardening \
  --mvtec-records runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl \
  --mvtec-adapter-summary runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_summary.json \
  --mvtec-pipeline-summary runs/mvtec_calibrated_pipeline/mvtec_calibrated_pipeline_summary.json \
  --wm811k-records runs/wm811k_real_recognition_smoke/wm811k_records.jsonl \
  --wm811k-adapter-summary runs/paper_case_studies/wm811k_traceability_real/adapter_pipeline_summary.json \
  --overwrite
```

Artifacts:

- `runs/paper_case_studies/evaluation_hardening/mvtec_object_selection.csv`
- `runs/paper_case_studies/evaluation_hardening/paper_case_study_evaluation_summary.json`

Selection result:

| Object | Records | Defects | Visual score | Mean IoU | Path coverage | KG score | Selection score |
|---|---:|---:|---:|---:|---:|---:|---:|
| `cable` | 9 | 8 | 1.00 | 0.2748 | 0.8889 | 0.8333 | 0.7939 |
| `metal_nut` | 4 | 3 | 1.00 | 0.2819 | 0.7500 | 0.8750 | 0.7689 |
| `carpet` | 6 | 5 | 1.00 | 0.3865 | 0.6667 | 0.8333 | 0.7606 |
| `grid` | 6 | 5 | 1.00 | 0.1763 | 0.8333 | 0.8333 | 0.7603 |
| `capsule` | 6 | 5 | 1.00 | 0.1967 | 0.6667 | 0.9167 | 0.7393 |
| `zipper` | 8 | 7 | 1.00 | 0.3857 | 0.3750 | 0.9375 | 0.7084 |

Selected object for the paper-facing visual evidence case: `cable`.

Rationale:

- All sampled `cable` defect rows are detected anomalous and the sampled good
  row is detected normal.
- The object selection was run over the 15-object calibrated local MVTec run.
  `cable` has the highest transparent selection score because it combines broad
  defect coverage, correct good/defect separation, strong path coverage, and
  adequate KG entity coverage.
- Its candidate explanation targets are diverse and reviewable:
  `AssemblyError`, `ContaminationCause`, `MechanicalContact`, and
  `MissingComponent`.
- `metal_nut` is a useful backup case if the paper needs a smaller but cleaner
  object example: it has fewer sampled cases but high KG/path coverage.

Claim boundary:

Use this as a visual-evidence plus KG-completion case. Do not describe the
selected MVTec target candidates as verified factory RCA labels.

## KG Quality Check

Command:

```bash
uv run python scripts/run_kg_qa.py \
  --output runs/paper_case_studies/kg_qa_report.json
```

Result:

- Nodes: 211.
- Edges: 602.
- Issues: 0.
- Warnings: 22.
- Passed: true.

Warning distribution:

- `isolated_node`: 18.
- `reviewed_low_confidence`: 4.

Suggested interpretation:

- Use the QA result to support that KG artifacts satisfy schema checks and
  provenance requirements.
- Do not hide warnings; mention that warnings identify curation opportunities,
  not blocking schema failures.

## Verification Commands

The following checks passed after the evaluation hardening changes:

```bash
uv run --extra dev ruff check src/kgtracevis/workflows/tep_evaluation.py tests/test_tep_evaluation.py
uv run --extra dev pytest tests/test_tep_evaluation.py
uv run --extra dev ruff check src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py tests/test_paper_case_studies.py
uv run --extra dev pytest tests/test_paper_case_studies.py
uv run --extra dev ruff check src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py scripts/build_wm811k_stratified_records.py tests/test_paper_case_studies.py
uv run --extra dev ruff format --check src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py scripts/build_wm811k_stratified_records.py tests/test_paper_case_studies.py
uv run --extra dev mypy src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py scripts/build_wm811k_stratified_records.py tests/test_paper_case_studies.py
uv run --extra dev pytest tests/test_paper_case_studies.py tests/test_adapter_pipeline.py tests/test_record_producers.py
uv run --extra dev pytest tests/test_paper_case_studies.py tests/test_mvtec_patchcore_experiment.py tests/test_paper_tables.py
uv run --extra dev mypy src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py tests/test_paper_case_studies.py src/kgtracevis/workflows/tep_evaluation.py tests/test_tep_evaluation.py
uv run --extra dev ruff check .
uv run --extra dev ruff format --check src/kgtracevis/workflows/paper_case_studies.py scripts/evaluate_paper_case_studies.py tests/test_paper_case_studies.py src/kgtracevis/workflows/tep_evaluation.py tests/test_tep_evaluation.py
uv run --extra dev mypy src tests scripts
uv run python scripts/run_examples.py
uv run --extra dev pytest
```

Results:

- Targeted TEP tests: 3 passed.
- Targeted paper case-study tests: 7 passed.
- Targeted stratified WM811K Ruff/Mypy checks: passed.
- Related producer/adapter/paper tests: 56 passed.
- Relevant paper/MVTec table tests: 16 passed.
- Targeted mypy: no issues in 5 source files.
- Full Ruff: passed.
- Full mypy: no issues in 174 source files.
- Full test suite: 270 passed.
- Example script validated 4 example cases.
- KG QA passed with 0 issues.

## Suggested Section 6 Reporting Strategy

Recommended table for TEP:

- Columns: setting, faults requested, faults observed, cases, top-1, top-3,
  top-5, MRR, path hit rate, label-ablation stability.
- Main row: all-fault smoke.
- Optional row: stable subset sanity check.

Recommended failure-analysis paragraph:

- Discuss fault 10 and 15 as top-k near misses.
- Discuss fault 18 as a current ranking/feature miss.
- Discuss fault 20 as an asset-coverage limitation because no Root-KGD anchor
  was found.

Recommended auxiliary-case table:

- Rows: wafer nearfull, wafer descriptor fallback, MVTec clean scratch, MVTec
  mask fallback.
- Columns: case, scenario, linked entities, paths, top candidate, source,
  claim boundary.

Important wording:

- Prefer "candidate root-cause hypothesis", "source-grounded path", and
  "reviewable explanation".
- Avoid "discovered true root cause" for wafer or MVTec.
- Avoid presenting label-ablation stability as proof of full causal validity;
  it only reduces concern about explicit fault-label leakage in runtime
  evidence.
