# Experiment Plan

For the paper-facing protocol and reference eligibility rules for the current
adapter-first MVTec/WM811K milestone, see
[`docs/paper_experiment_protocol.md`](paper_experiment_protocol.md).

The stable v0 runtime path is:

```text
example JSON -> KG link -> consistency score -> correction -> path ranking -> demo
```

The current adapter-first paper milestone starts from checked-in
producer-output-style records and then uses the same runtime pipeline:

```text
producer-output records -> Evidence adapters -> Evidence JSON -> KGTracePipeline
-> candidate/plausible explanation paths
```

Formal experiments should run through scripts, save their configs, and write
outputs under `runs/` or `outputs/`.

## V0 Scripts

- `uv run python scripts/run_examples.py` validates the checked-in examples and
  runs the full `KGTracePipeline`.
- `uv run python scripts/run_noise_experiment.py` writes deterministic noise
  reproducibility summaries under `runs/<experiment_name>/`.
- `uv run python scripts/run_path_ranking.py` prints concise top-k path ranking
  summaries for all checked-in examples.
- `uv run python scripts/run_path_ranking.py --evidence <path> --write-json`
  analyzes one evidence file and writes a provenance-rich JSON summary under
  `outputs/path_ranking_v0/`.
- `uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json`
  writes structured KG CSV issues and warnings without editing KG facts.
- `uv run python scripts/run_adapter_pipeline.py --input data/examples/records/mvtec_records.jsonl --dataset mvtec --output-dir outputs/adapter_pipeline_v0/mvtec --overwrite`
  converts MVTec producer-output-style records to Evidence, runs
  `KGTracePipeline`, and writes generated Evidence JSON files, a
  provenance-rich summary JSON, and a scoped CSV table.
- `uv run python scripts/run_adapter_pipeline.py --input data/examples/records/wm811k_records.jsonl --dataset wafer --output-dir outputs/adapter_pipeline_v0/wm811k --overwrite`
  does the same for WM811K while keeping the shared wafer schema boundary.
- `uv run python scripts/run_experiment_suite.py` runs the local v0 script
  suite, including both adapter pipeline stages, and writes a consolidated JSON
  summary plus `table_summary.csv` under `runs/v0_experiment_suite/`.
- `uv run python scripts/build_paper_tables.py --overwrite` reads the current
  suite, adapter-pipeline, and noise summaries and writes grouped paper-facing
  manifests under `artifacts/paper_tables_v0/`. The manifest groups generated
  rows by dataset, noise type, annotation/reference type, and metric scope, and
  records source commands plus source artifact paths for review.

Generated `runs/`, `outputs/`, and `artifacts/` content is ignored by Git. Do
not commit these raw generated outputs. If a generated table, figure, or JSON
snippet is selected for the paper, review it, copy only the stable derived asset
into `paper/figures/` or `paper/tables/`, and record the source command plus
input path in the paper asset notes.

## Metric Scope

The v0 script metrics are reproducibility checks over checked-in examples or
clean-run references. They are not paper-grade ground-truth claims unless an
external ground-truth reference set is curated, documented, and wired into the
experiment configuration.

For MVTec and public WM811K, root-cause/path-ranking outputs must be reported as
candidate or curated plausible explanations unless the reference row is
externally reviewed or otherwise upgraded. Schema, linking, consistency,
correction, and noise results may be used as controlled reproducibility metrics
over the checked-in examples.

## Paper-Facing Manifests

The paper table builder is a manifest generator, not a paper asset copier. It
does not write into `paper/` automatically.

Default inputs:

- `runs/v0_experiment_suite/adapter_pipeline_mvtec/adapter_pipeline_summary.json`
- `runs/v0_experiment_suite/adapter_pipeline_wm811k/adapter_pipeline_summary.json`
- `runs/v0_examples/summary.json`
- `runs/v0_experiment_suite/summary.json`

Default outputs:

- `artifacts/paper_tables_v0/paper_manifest.csv`
- `artifacts/paper_tables_v0/command_manifest.csv`
- `artifacts/paper_tables_v0/paper_tables_summary.json`

`paper_manifest.csv` includes `dataset`, `noise_type`, `annotation_type`,
`metric_scope`, `source_artifact`, `source_command`, `record_count`,
`case_count`, and `claim_boundary`. For MVTec and WM811K/wafer rows, path and
candidate target outputs remain bounded as plausible explanations rather than
verified RCA.
