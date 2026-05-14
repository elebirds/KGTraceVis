# Paper Experiment Protocol

Status: paper-facing protocol for the current adapter-first MVTec/WM811K
milestone. It defines what current outputs may support in a paper draft and
what claims remain out of scope.

## Pipeline Under Evaluation

The current milestone evaluates this path:

```text
producer-output records
-> Evidence adapters
-> validated Evidence JSON
-> KGTracePipeline
-> linked entities
-> consistency score and inconsistent fields
-> correction candidates
-> top-k candidate/plausible explanation paths
-> scoped JSON/CSV tables
```

Producer-output records are normalized, model-output-style rows. They may come
from deterministic fixtures now and from detectors/classifiers later. Evidence
adapters are model-independent and must emit observed evidence only. They do
not emit root causes, ranked paths, or prefilled `kg_analysis`; those are
runtime outputs from `KGTracePipeline`.

## Current Dataset Boundaries

MVTec / DS-MVTec:

- Supported now for visual defect evidence normalization.
- Paper-safe metrics include schema validity, entity linking, morphology and
  location consistency, correction, and noise recovery over checked-in examples.
- Path outputs are candidate explanations against curated plausible references.
- Do not claim MVTec native labels are verified factory RCA labels.

WM811K as wafer:

- Supported now through the shared `dataset="wafer"` schema boundary, with
  WM811K identified by adapter metadata such as `adapter.name="wm811k"`.
- Paper-safe metrics include wafer spatial-pattern evidence, location/zone,
  morphology, severity, confidence, linking, consistency, correction, and noise
  recovery over checked-in examples.
- Public WM811K supports spatial pattern classification much more directly than
  process RCA. Path outputs are candidate/plausible explanations unless a row
  is externally reviewed or backed by stronger process references.
- Do not claim verified RCA accuracy for public WM811K native labels.

TEP:

- Is the current primary quantitative RCA/path-ranking scenario.
- TEP fault numbers may be used as evaluation references because the benchmark
  defines process fault types, but they must not be used as scoring input.
- Native TEP RCA runs through the same `KGTracePipeline` output contract:
  adapter evidence plus `tep`/`shared` KG support paths produce both
  `ranked_root_causes` and `top_k_paths`.

## Reference Eligibility Rules

Use references only according to their annotation and evaluation scope.

| Reference type | Eligible paper use | Not eligible for |
| --- | --- | --- |
| `native_ground_truth` | Dataset-observed labels such as defect class or spatial pattern, when the dataset defines them. | Process RCA unless the dataset explicitly supplies reviewed RCA. |
| `official_fault_type` | Fault/event labels for scenarios where the benchmark defines process faults. | Treating visual anomaly classes as root causes. |
| `literature_supported` | Secondary evidence or bounded candidate explanations when source text is recorded. | Strong claims without traceable source and review status. |
| `manual_plausible` | Case-study explanation, plausible-reference path hit, and demo review. | Primary verified RCA accuracy. |
| `demo_synthetic` | Reproducibility smoke tests and UI/demo examples. | Paper ground-truth tables. |
| `llm_candidate` | Candidate extraction backlog after validation and review. | Any ground-truth metric before review. |

Schema, linking, consistency, correction, and noise metrics may be reported as
v0 reproducibility metrics over checked-in examples or clean-run references.
They should be described as controlled example metrics unless a larger external
reference set is curated.

Path-ranking metrics for MVTec and WM811K must be labeled as `candidate`,
`plausible`, or `curated plausible reference` unless the target row has
external review or verified process evidence. Top-k path hit, MRR, and path hit
rate are acceptable only when the table names the reference scope.

Current reference files:

| File | Current scope | Eligible metric wording |
| --- | --- | --- |
| `data/references/mvtec_plausible_rca_reference.csv` | Curated plausible visual explanation references for MVTec-style cases. | `path hit against curated plausible references`; not verified factory RCA. |
| `data/references/wafer_plausible_reference.csv` | Wafer/WM811K traceability demo references. | `candidate/plausible explanation case study`; not public verified process RCA. |
| `data/references/tep_rca_reference.csv` | TEP process-fault style demo references and fault-label evaluation scope. | TEP top-k RCA accuracy, MRR, and path hit when the command records producer inputs and confirms fault labels are evaluation-only. |

## Command And Artifact Map

Use these commands for the current paper-facing artifacts.

| Command | Main artifacts | Paper-use eligibility |
| --- | --- | --- |
| `uv run python scripts/run_adapter_pipeline.py --input data/examples/records/mvtec_records.jsonl --dataset mvtec --output-dir outputs/adapter_pipeline_v0/mvtec --overwrite` | `adapter_pipeline_summary.json`, `adapter_pipeline_table.csv`, generated Evidence JSON files | MVTec adapter-to-pipeline reproducibility, evidence/linking/consistency/correction rows, and plausible explanation case-study rows. |
| `uv run python scripts/run_adapter_pipeline.py --input data/examples/records/wm811k_records.jsonl --dataset wafer --output-dir outputs/adapter_pipeline_v0/wm811k --overwrite` | `adapter_pipeline_summary.json`, `adapter_pipeline_table.csv`, generated Evidence JSON files | WM811K-as-wafer adapter-to-pipeline reproducibility, spatial evidence rows, and plausible explanation case-study rows. |
| `uv run python scripts/run_experiment_suite.py` | `runs/v0_experiment_suite/summary.json`, `runs/v0_experiment_suite/table_summary.csv`, `runs/v0_experiment_suite/adapter_pipeline_*/adapter_pipeline_table.csv` | Consolidated provenance for v0 commands; useful as a run manifest and paper table source after human review. |
| `uv run python scripts/build_paper_tables.py --overwrite` | `artifacts/paper_tables_v0/paper_manifest.csv`, `artifacts/paper_tables_v0/command_manifest.csv`, `artifacts/paper_tables_v0/paper_tables_summary.json` | Grouped paper-facing manifest by dataset, noise type, annotation/reference type, and metric scope. This records source command provenance but does not copy files into `paper/`. |
| `uv run python scripts/run_noise_experiment.py` | `runs/<experiment_name>/summary.json` and noise outputs | Controlled noise/correction reproducibility over checked-in examples. |
| `uv run python scripts/run_path_ranking.py --write-json` | `outputs/path_ranking_v0/path_ranking_summary.json` | Path ranking provenance; MVTec/WM811K rows remain plausible-reference or case-study outputs. |
| `uv run python scripts/evaluate_tep_rca.py --output-dir runs/tep_raw_batch_eval_unified --raw-data-dir data/raw/tep --faults 1,2,6 --overwrite` | `tep_rca_evaluation_summary.json`, `tep_rca_evaluation_cases.csv`, generated TEP producer records, adapter pipeline summary | Current TEP RCA/path-ranking metric surface. Fault labels are evaluation references only; RCA scoring uses adapter variable evidence and KG support paths. |
| `uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json` | KG issue/warning report | Provenance and sanity check for KG CSV quality; not an experiment metric by itself. |

Generated files under `runs/`, `outputs/`, and `artifacts/` are not committed.
Only reviewed stable paper assets should be copied into `paper/figures/` or
`paper/tables/`, with the source command and input path recorded nearby.

## Reporting Checklist

- State that KGTraceVis evaluates evidence normalization and source-constrained
  KG reasoning, not a new anomaly detector.
- Name each metric scope: `v0_reproducibility_output`,
  `checked_in_example`, `manual_plausible`, `demo_synthetic`, or the exact
  reviewed reference scope.
- Keep MVTec and WM811K RCA wording as candidate/plausible unless externally
  reviewed.
- Report adapter provenance: input record file, generated Evidence path,
  adapter name, KG source edges, and output table path.
- Use `paper_manifest.csv` as the first review surface for selected tables:
  check `source_artifact`, `source_command`, `annotation_type`, `metric_scope`,
  and `claim_boundary` before copying any stable table into `paper/`.
- For TEP RCA tables, report the evaluation command, `tep_records.jsonl`, KG
  node/edge paths or Neo4j runtime status, and the statement that fault labels
  were withheld from scoring and used only for metric computation.
