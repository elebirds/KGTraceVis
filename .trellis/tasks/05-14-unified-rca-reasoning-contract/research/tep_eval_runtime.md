# Research: TEP evaluation and runtime hooks

- Query: Research the existing TEP raw producer, adapter pipeline, metrics/evaluation helpers, Neo4j import hooks, and TEP RCA tests for a unified RCA reasoning contract.
- Scope: internal
- Date: 2026-05-14

## Findings

### Files found

- `scripts/build_dataset_records.py` - CLI for producer-output JSONL generation; exposes TEP flags for raw CSV path, fault subset, window size, row stride, profile row cap, run cap, top variables, and PCA components.
- `src/kgtracevis/workflows/dataset_records.py` - reusable workflow behind the CLI; routes `dataset="tep"` to the TEP raw producer and writes a profile artifact beside the JSONL.
- `src/kgtracevis/producers/tep_records.py` - raw TEP CSV producer; fits fault-free reconstruction profile, streams faulty windows, computes residual contribution variables, and emits adapter-ready records without root-cause outputs.
- `src/kgtracevis/adapters/tep_adapter.py` - TEP Evidence adapter; maps records into unified `Evidence`, preserves fault/run/window metadata in raw evidence extra, and emits variable observations with contribution values.
- `src/kgtracevis/adapters/batch.py` - JSON/JSONL/CSV record loader and dataset adapter dispatcher.
- `src/kgtracevis/experiments/adapter_pipeline.py` - adapter-to-pipeline workflow; writes evidence files, `adapter_pipeline_summary.json`, and `adapter_pipeline_table.csv`.
- `scripts/run_adapter_pipeline.py` - CLI wrapper for the adapter pipeline; exposes TEP RCA provider selection (`none`, `native`, `artifact`).
- `src/kgtracevis/metrics/ranking_metrics.py` - top-k root-cause accuracy, MRR, and path hit rate helpers.
- `src/kgtracevis/metrics/linking_metrics.py` and `src/kgtracevis/metrics/correction_metrics.py` - related top-k metric helpers for entity linking and corrections.
- `src/kgtracevis/workflows/tep_rca.py` - native and artifact-backed TEP RCA providers.
- `scripts/import_kg.py` and `src/kgtracevis/kg/import_neo4j.py` - Neo4j import CLI and implementation.
- `src/kgtracevis/kg/neo4j_repository.py` - runtime Neo4j snapshot repository used by `KGTracePipeline` when no explicit graph is supplied.
- `tests/test_record_producers.py` - TEP raw producer and workflow coverage.
- `tests/test_tep_native_rca_provider.py` - native TEP RCA provider and pipeline integration coverage.
- `tests/test_adapter_pipeline.py` - adapter pipeline output shape and TEP provider CLI selection coverage.
- `tests/test_tep_rca_bridge.py` - artifact-backed TEP RCA provider selector and no-global-leakage coverage.
- `tests/test_import_neo4j.py` and `tests/test_neo4j_repository.py` - import/repository behavior with fake sessions/drivers.

### TEP raw producer and batch generation

- `scripts/build_dataset_records.py:32` accepts `--dataset tep`; if no `--model-backend` is provided, TEP defaults to `tep-rbc` at `scripts/build_dataset_records.py:153`.
- TEP CLI flags are defined at `scripts/build_dataset_records.py:103` through `scripts/build_dataset_records.py:150`, including explicit fault-free/faulty CSV paths, fault subset, window size, row stride, profile row cap, run cap, top variable count, and component count.
- The workflow routes TEP at `src/kgtracevis/workflows/dataset_records.py:92` through `src/kgtracevis/workflows/dataset_records.py:95` and calls `build_tep_records` with default `data/raw/tep` fallback plus profile output at `src/kgtracevis/workflows/dataset_records.py:261` through `src/kgtracevis/workflows/dataset_records.py:274`.
- The producer expects `TEP_FaultFree_Training.csv` and `TEP_Faulty_Training.csv` under the raw directory (`src/kgtracevis/producers/tep_records.py:19`, `src/kgtracevis/producers/tep_records.py:20`) and defaults faults to 1..21 (`src/kgtracevis/producers/tep_records.py:21`).
- It validates positive sampling/window options, fits the fault-free profile, collects fixed-size faulty windows, and computes top residual contribution variables (`src/kgtracevis/producers/tep_records.py:88` through `src/kgtracevis/producers/tep_records.py:124`).
- Record output includes `dataset="tep"`, `source="tep_csv_rbc"`, `adapter="tep"`, `case_id`, `anomaly_type="fault_NN"`, `morphology="multivariate_residual_shift"`, `fault_number`, `simulation_run`, window metadata, top variables, contribution scores, detector metadata, and `produces_root_cause=False` (`src/kgtracevis/producers/tep_records.py:301` through `src/kgtracevis/producers/tep_records.py:351`).
- The local raw data exists at `data/raw/tep` with the required training CSVs. Sizes observed: fault-free training about 89 MB; faulty training about 1.7 GB. Use `--faults`, `--max-cases`, `--tep-max-runs-per-fault`, and `--tep-fault-free-max-rows` for manageable runs.

Exact manageable generation command:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset tep \
  --input-root data/raw/tep \
  --output-jsonl data/processed/records/tep_rbc_eval_subset.jsonl \
  --faults 1,6,14 \
  --tep-window-size 100 \
  --tep-row-stride 50 \
  --tep-fault-free-max-rows 5000 \
  --tep-max-runs-per-fault 2 \
  --tep-top-variables 8 \
  --tep-n-components 6 \
  --max-cases 6 \
  --overwrite
```

Then run the existing adapter pipeline with native TEP RCA:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/processed/records/tep_rbc_eval_subset.jsonl \
  --dataset tep \
  --output-dir runs/tep_eval_subset \
  --top-k 5 \
  --tep-rca-provider native \
  --overwrite
```

For a file-backed graph rather than Neo4j runtime, add:

```bash
  --kg-node-path data/kg/tep_nodes.csv \
  --kg-edge-path data/kg/tep_edges.csv
```

Note: custom KG paths are appended to default KG layers inside `run_adapter_pipeline`, not used as the only graph, because `_pipeline_from_kg_paths` prepends `DEFAULT_NODE_PATHS` and `DEFAULT_EDGE_PATHS` (`src/kgtracevis/experiments/adapter_pipeline.py:223` through `src/kgtracevis/experiments/adapter_pipeline.py:239`).

### Adapter pipeline shape and expected TEP labels

- Adapter pipeline outputs:
  - `adapter_pipeline_summary.json`
  - `adapter_pipeline_table.csv`
  - one Evidence JSON per case under `evidence/`
  (`src/kgtracevis/experiments/adapter_pipeline.py:23` through `src/kgtracevis/experiments/adapter_pipeline.py:26`).
- Table columns are fixed at `src/kgtracevis/experiments/adapter_pipeline.py:28` through `src/kgtracevis/experiments/adapter_pipeline.py:45`: `case_id`, `dataset`, `adapter_name`, `anomaly_type`, `location`, `morphology`, `consistency_score`, `linked_entity_count`, `correction_candidate_count`, `path_count`, top target fields, `best_score`, `explanation_scope`, and `claim_boundary`.
- Summary case records include compact evidence, linked entities, consistency details, correction candidates, `top_k_paths`, `ranked_root_causes`, candidate explanation targets, and source edge provenance (`src/kgtracevis/experiments/adapter_pipeline.py:284` through `src/kgtracevis/experiments/adapter_pipeline.py:317`).
- The TEP adapter accepts anomaly keys including `anomaly_type`, `fault_type`, `fault`, and `label`, and variable/contribution aliases (`src/kgtracevis/adapters/tep_adapter.py:24` through `src/kgtracevis/adapters/tep_adapter.py:39`).
- The raw producer emits TEP anomaly labels as `fault_01`, `fault_02`, ... (`src/kgtracevis/producers/tep_records.py:312`), while `data/kg/tep_nodes.csv` contains FaultType aliases for `fault_01` through `fault_19` and IDV forms. The checked-in seed currently has fault nodes 1..19, not 20..21.
- TEP source boundaries are documented in `docs/sources/tep_sources.md:7` through `docs/sources/tep_sources.md:21`: TEP_KG fault labels are reviewable candidate RCA support, not online causal proof.

### Metrics and evaluation helpers

- Root-cause metric helpers already exist:
  - `top_k_root_cause_accuracy` at `src/kgtracevis/metrics/ranking_metrics.py:13`
  - `mean_reciprocal_rank` at `src/kgtracevis/metrics/ranking_metrics.py:34`
  - `path_hit_rate` at `src/kgtracevis/metrics/ranking_metrics.py:52`
- These helpers accept strings or dictionaries; ranking dictionaries can expose `target_entity_id`, `entity_id`, `selected_entity_id`, or `root_cause_id` (`src/kgtracevis/metrics/ranking_metrics.py:73` through `src/kgtracevis/metrics/ranking_metrics.py:96`). Path hits use `path_id` first, then node/relation signatures (`src/kgtracevis/metrics/ranking_metrics.py:99` through `src/kgtracevis/metrics/ranking_metrics.py:114`).
- Entity-linking top-k metrics are in `src/kgtracevis/metrics/linking_metrics.py:26` through `src/kgtracevis/metrics/linking_metrics.py:44`.
- Correction/noise top-k helpers are in `src/kgtracevis/metrics/correction_metrics.py:23` through `src/kgtracevis/metrics/correction_metrics.py:46`.
- `tests/test_metrics.py:82` through `tests/test_metrics.py:96` cover root-cause top-k accuracy, MRR, and path hit rate.

Recommended implementation points for a TEP evaluation summary:

1. Add a reusable workflow/helper under `src/kgtracevis/workflows/` or `src/kgtracevis/experiments/`, not directly in `scripts/`, matching the workflow pattern from `.trellis/spec/backend/workflow-architecture.md`.
2. Input should be the adapter pipeline summary JSON or the `AdapterPipelineOutput.summary` mapping, because it already contains `ranked_root_causes`, `top_k_paths`, and compact generated evidence per case.
3. Normalize expected labels from evidence using `fault_number`/`anomaly_type` to KG node IDs where possible. For `fault_06`, expected KG ID is `Fault06Stream1AFeedLoss`; for all v1 labels use aliases in `data/kg/tep_nodes.csv`, not ad hoc string matching.
4. Emit summary fields: case_count, eligible_case_count, top-1/top-3/top-5 root-cause accuracy, MRR, path hit rate when a path reference is available, per-fault breakdown, missing-reference cases, and claim-boundary text.
5. Reuse `top_k_root_cause_accuracy`, `mean_reciprocal_rank`, and `path_hit_rate` rather than reimplementing metrics.
6. Add a thin `scripts/summarize_tep_eval.py` wrapper only after the reusable helper exists.

### Neo4j import and runtime hooks

- Default KG CSV layers are `data/kg/nodes.csv`, `data/kg/mvtec_nodes.csv`, `data/kg/tep_nodes.csv`, `data/kg/wafer_nodes.csv` and corresponding edge layers including `data/kg/tep_edges.csv` (`src/kgtracevis/kg/graph.py:39` through `src/kgtracevis/kg/graph.py:51`).
- `scripts/import_kg.py` can import default layers or custom layers; `--include-defaults` appends custom paths to defaults (`scripts/import_kg.py:21` through `scripts/import_kg.py:40`, `scripts/import_kg.py:54` through `scripts/import_kg.py:72`).
- `--dry-run` validates and counts rows without connecting (`scripts/import_kg.py:47` through `scripts/import_kg.py:50`, `scripts/import_kg.py:84` through `scripts/import_kg.py:85`).
- Real import resolves CLI args, environment, then YAML config (`src/kgtracevis/kg/import_neo4j.py:82` through `src/kgtracevis/kg/import_neo4j.py:108`) and requires complete URI/user/password/database (`src/kgtracevis/kg/import_neo4j.py:216` through `src/kgtracevis/kg/import_neo4j.py:227`).
- Import creates a unique constraint/index, `MERGE`s `KGEntity` nodes, and `MERGE`s typed relations by `edge_id` while setting provenance/confidence/review/feedback fields (`src/kgtracevis/kg/import_neo4j.py:24` through `src/kgtracevis/kg/import_neo4j.py:41`, `src/kgtracevis/kg/import_neo4j.py:241` through `src/kgtracevis/kg/import_neo4j.py:274`).
- Runtime pipeline now uses Neo4j by default when no explicit graph/repository is supplied: `KGTracePipeline.graph_for_evidence` connects to `Neo4jKGRepository.connect(resolve_neo4j_config())` at `src/kgtracevis/core/pipeline.py:88` through `src/kgtracevis/core/pipeline.py:105`.
- `Neo4jKGRepository.to_knowledge_graph` scopes snapshots to selected dataset plus `shared` (`src/kgtracevis/kg/neo4j_repository.py:239` through `src/kgtracevis/kg/neo4j_repository.py:252`).

Observed local Neo4j status:

- `uv run python scripts/import_kg.py --dry-run` succeeded with 210 nodes and 602 edges.
- `uv run python scripts/import_kg.py --dry-run --nodes data/kg/tep_nodes.csv --edges data/kg/tep_edges.csv` succeeded with 74 nodes and 216 edges.
- `uv run python -c "import neo4j; print(neo4j.__version__)"` printed `6.1.0`.
- `nc -z localhost 7687` succeeded.
- A read-only `driver.verify_connectivity()` using `configs/neo4j.example.yaml` succeeded for `bolt://localhost:7687`, user `neo4j`, database `neo4j`.
- No `NEO4J_*` environment variables were present in this shell.

Current obstacles to real Neo4j import:

- No code-level blocker was observed locally; dependencies are installed, Bolt is reachable, and default example credentials verified connectivity.
- Real import was not executed during this research because it mutates the local Neo4j database.
- Import is `MERGE`/upsert-oriented and does not clear stale graph rows. If the database already contains older KG rows, run-level evaluation may see stale nodes/edges unless the database is cleared or imported into a clean database.
- `configs/kg_config.yaml` stores env-var names (`uri_env`, `user_env`, `password_env`), but the import resolver expects direct `uri`, `user`, `password`, `database` keys or actual `NEO4J_*` environment variables. Use `configs/neo4j.example.yaml`, CLI flags, or exported env vars for import.

Real import command, if mutation is intended:

```bash
uv run python scripts/import_kg.py
```

TEP-only import command, if mutation is intended:

```bash
uv run python scripts/import_kg.py \
  --nodes data/kg/tep_nodes.csv \
  --edges data/kg/tep_edges.csv
```

Default-plus-explicit TEP overlay command, if mutation is intended:

```bash
uv run python scripts/import_kg.py \
  --include-defaults \
  --nodes data/kg/tep_nodes.csv \
  --edges data/kg/tep_edges.csv
```

### Tests to run

Focused tests for this slice:

```bash
uv run --extra dev pytest tests/test_record_producers.py \
  tests/test_adapter_pipeline.py \
  tests/test_tep_native_rca_provider.py \
  tests/test_tep_rca_bridge.py \
  tests/test_metrics.py \
  tests/test_import_neo4j.py \
  tests/test_neo4j_repository.py
```

Additional dry-run checks:

```bash
uv run python scripts/import_kg.py --dry-run
uv run python scripts/import_kg.py --dry-run --nodes data/kg/tep_nodes.csv --edges data/kg/tep_edges.csv
```

If the evaluation helper/script is added, add a focused test using a tiny synthetic adapter summary and run the relevant workflow/script lint:

```bash
uv run --extra dev ruff check src/kgtracevis/workflows scripts
uv run --extra dev mypy src tests scripts
```

## Caveats / Not Found

- I did not run the raw TEP record-generation command because the researcher-agent write boundary allows writes only under the task `research/` directory.
- I did not run real Neo4j import because it mutates the local Neo4j database.
- I did not find an existing TEP-specific evaluation summary helper or CLI; only general metric functions and adapter-pipeline summaries exist.
- `data/references/tep_rca_reference.csv` currently contains only demo-scale references for `tep_0001`, not a curated full TEP evaluation set.
- The TEP seed KG has checked-in fault aliases for faults 1..19, while the producer defaults to faults 1..21. Evaluation should restrict to faults with references/KG aliases or add reviewed seed coverage before scoring faults 20/21.
