# KGTraceVis

KGTraceVis is a research prototype for knowledge-enhanced industrial anomaly
detection and root-cause traceability.

The project converts heterogeneous anomaly outputs from images, process time
series, and wafer logs into a unified anomaly evidence JSON schema. It then uses
a source-constrained industrial knowledge graph to support entity linking,
evidence consistency scoring, noisy evidence correction, relation-weighted
root-cause path ranking, and visual analytics.

For the current Chinese research design draft, see
[`docs/paper_idea_cn.md`](docs/paper_idea_cn.md). This document is a living
draft and may change as the project evolves. For the current adapter-first
paper experiment protocol and reference eligibility rules, see
[`docs/paper_experiment_protocol.md`](docs/paper_experiment_protocol.md).

## Design Position

KGTraceVis should stay small and reproducible in v0.

The stable v0 runtime path is:

```text
example JSON -> KG link -> consistency score -> correction -> path ranking -> API
```

The current paper-facing adapter milestone uses the same runtime pipeline but
starts one step earlier:

```text
producer-output records -> Evidence adapters -> Evidence JSON -> KGTracePipeline
-> scenario-aware candidate/plausible RCA reasoning
```

The optional real-data producer layer can now build normalized JSONL records
from local MVTec-like image folders and WM811K tables before those records enter
the adapter layer. See
[`docs/dataset_record_producers.md`](docs/dataset_record_producers.md) for the
record contract and local smoke commands.

The project should not start with a large front-end system, user management, or
complex online learning. Instead, scripts and future apps must share the same
reusable core pipeline.

```text
Scripts are clients.
The FastAPI service is also a client.
The reusable pipeline is the product.
```

## Usage Modes

KGTraceVis supports two usage modes:

1. Batch / script mode:
   KG construction, evidence validation, noise experiments, path ranking, and
   metric evaluation.
2. Interactive visual analytics mode:
   evidence inspection, correction review, path comparison, and human feedback
   through the maintained FastAPI backend and the React workbench under `web/`.

The old React/Vite dashboard is preserved under `web_legacy/` as a migration
reference. The maintained `web/` client is a clean React + TypeScript + Vite
workspace using Arco React and ECharts while consuming the FastAPI contracts
without owning reusable analysis logic.

## Repository Layout

```text
KGTraceVis/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── .gitignore
├── Makefile
├── configs/
├── src/
│   └── kgtracevis/
│       ├── core/
│       ├── schema/
│       ├── adapters/
│       ├── kg_construction/
│       ├── kg/
│       ├── mask/
│       ├── noise/
│       ├── metrics/
│       ├── viz/
│       ├── feedback/
│       └── service/
├── scripts/
├── data/
│   ├── examples/
│   ├── kg/
│   ├── external/
│   ├── interim/
│   └── processed/
├── runs/
├── outputs/
├── artifacts/
├── notebooks/
├── docs/
├── paper/
└── tests/
```

## What Is Tracked

Tracked:

- source code under `src/kgtracevis/`
- command entry points under `scripts/`
- tests under `tests/`
- small configs under `configs/`
- tiny example evidence under `data/examples/`
- small curated KG CSV files under `data/kg/`
- docs and paper source files
- `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`

Not tracked:

- full raw datasets
- model weights
- intermediate processing files
- generated predictions
- experiment runs
- generated figures and reports
- Neo4j local database files
- LaTeX build outputs

## Data Layout

Large datasets are not committed.

Place datasets as follows:

- Defect Spectrum / DS-MVTec: `data/external/ds_mvtec/`
- Tennessee Eastman Process raw CSV: `data/raw/tep/`
- Wafer data: `data/external/wafer/`

Use this convention:

```text
data/external/     original datasets, not tracked
data/raw/          large raw source datasets, not tracked
data/interim/      intermediate processing outputs, not tracked
data/processed/    generated reproducible outputs, not tracked
data/kg/           small curated KG CSV files, tracked
data/examples/     tiny evidence examples, tracked
```

## Environment

This project uses uv with one Python package and optional dependency groups.
Do not introduce a uv workspace unless the repository is later split into
multiple independently maintained packages.

Install the base environment:

```bash
uv sync
```

Install all optional dependencies for development:

```bash
uv sync --all-extras
```

Create a local `.env` from `.env.example`:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
KGTRACE_POSTGRES_DSN=postgresql://kgtracevis:kgtracevis@localhost:5432/kgtracevis
```

## Database Runtime

The runtime database direction is:

```text
Neo4j     runtime KG storage and graph traversal
Postgres  evidence cases, analysis runs, feedback, drafts, review state
CSV/JSON   seed/import/export artifacts for reproducibility, not runtime state
```

API run history and feedback use Postgres as the source of truth. Uploaded
input files and generated artifacts may still be written under `runs/`, but the
default `/api/runs` and `/api/feedback` paths do not read or append legacy
session JSON files.

Start the local services:

```bash
docker compose up -d neo4j postgres
```

Initialize Postgres and import the KG seed files into Neo4j:

```bash
uv run python scripts/init_postgres.py
uv run python scripts/import_kg.py
```

For a containerized backend plus databases:

```bash
docker compose up --build
```

The Docker Compose stack initializes the Postgres schema, imports the KG seed
rows into Neo4j, then starts the API. It exposes Neo4j Browser at
`http://localhost:7474`, Neo4j Bolt at `bolt://localhost:7687`, Postgres at
`localhost:5432`, and the FastAPI backend at `http://localhost:8000`.
Analysis loads a dataset-scoped KG snapshot from Neo4j at runtime.

## Common Commands

Validate example evidence:

```bash
uv run python scripts/run_examples.py
```

TEP Root-KGD RCA is the single supported TEP RCA mode in `KGTracePipeline`.
Generic adapter/upload workflows do not expose provider mode switches.
`scripts/run_examples.py` remains a lightweight evidence/KG smoke.

Compile source materials into KG CSV files:

```bash
uv run python scripts/compile_source_kg.py --source docs/sources --output-dir runs/source_kg/manual --overwrite
```

Import KG into Neo4j:

```bash
uv run python scripts/import_kg.py
```

Initialize the Postgres application-state schema:

```bash
uv run python scripts/init_postgres.py
```

Run noise experiment:

```bash
uv run python scripts/run_noise_experiment.py
```

Run the consolidated v0 suite:

```bash
uv run python scripts/run_experiment_suite.py
```

The suite also runs the checked-in MVTec and WM811K adapter records through
`KGTracePipeline`, writing per-dataset adapter summaries and CSV tables under
`runs/v0_experiment_suite/adapter_pipeline_*`.

Build grouped paper-facing manifests from current generated outputs:

```bash
uv run python scripts/build_paper_tables.py --overwrite
```

This writes ignored review artifacts under `artifacts/paper_tables_v0/` with
dataset/noise/reference-scope grouping and command provenance. It does not copy
anything into `paper/`.

Run the maintained RootLens dashboard smoke:

```bash
uv run python scripts/smoke_rootlens_dashboard.py
```

See [`docs/rootlens_dashboard.md`](docs/rootlens_dashboard.md) for local API,
Vite, example upload, and review-feedback workflow details.

Build local producer-output records before adapter ingestion:

```bash
make download-model-assets
make download-patchcore

uv run python scripts/download_model_assets.py --model mvtec-stfpm
uv run python scripts/download_model_assets.py --model mvtec-patchcore
uv run python scripts/download_model_assets.py --model mvtec-efficientad \
  --mvtec-efficientad-repo <trusted-hf-repo> \
  --mvtec-efficientad-file <checkpoint-file>
uv run python scripts/download_model_assets.py --model wm811k-resnet --include-wm811k-data

uv run python scripts/build_dataset_records.py --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_subset.jsonl \
  --model-backend anomalib-engine \
  --checkpoint runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt \
  --device cpu \
  --overwrite

uv run python scripts/build_dataset_records.py --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_amazon_patchcore.jsonl \
  --model-backend amazon-patchcore \
  --object-checkpoint-root /path/to/patchcore/models \
  --device cpu \
  --overwrite

uv run python scripts/build_dataset_records.py --dataset wm811k \
  --input runs/real_model_pipeline/assets/wm811k/input_tables/test.pkl \
  --output-jsonl data/processed/records/wm811k_subset.jsonl \
  --model-backend torch-resnet34 \
  --checkpoint runs/real_model_pipeline/assets/wm811k/checkpoints/best_radai_resnet.pt \
  --model-source-repo radai-agent/radai-wm811k-defect-detection \
  --model-source-file best_radai_resnet.pt \
  --overwrite

uv run python scripts/build_dataset_records.py --dataset tep \
  --input-root data/raw/tep \
  --output-jsonl data/processed/records/tep_rbc_subset.jsonl \
  --faults 1,2,6 \
  --tep-window-size 100 \
  --tep-max-runs-per-fault 3 \
  --max-cases 9 \
  --overwrite
```

Command-line producer backends are real local backends; deterministic fake
predictors remain only in the test suite. Anomalib is imported only for
`anomalib-engine`, `anomalib-torch`, or `anomalib-openvino`; sklearn joblib or
pickle checkpoints must be trusted local files. The public WM811K ResNet asset
is a defect-pattern classifier over the labeled WM811K patterns only; it does
not provide verified root-cause labels or a normal-wafer detector.
TEP defaults to the native `tep-rbc` residual-contribution backend and does not
need a checkpoint.
`--include-wm811k-data` downloads the public Hugging Face dataset table
`lslattery/wafer-defect-detection` / `test.pkl` into
`runs/real_model_pipeline/assets/wm811k/input_tables/`; override it with
`--wm811k-input-repo`, `--wm811k-input-file`, and `--wm811k-input-repo-type`.
The downloader stores trusted public model assets under
`runs/real_model_pipeline/assets/`, including the default MVTec STFPM OpenVINO
checkpoint used by FastAPI image upload mode and a default capsule PatchCore Lightning
checkpoint from `NTHoang2103/patchcore-mvtec-models`. EfficientAD downloads
are wired into the same preset path, but require an explicitly trusted
Hugging Face repo/file or `KGTRACEVIS_DOWNLOAD_MVTEC_EFFICIENTAD_REPO` because
public EfficientAD files are usually component weights rather than one
Anomalib-compatible inference checkpoint.
Official Amazon PatchCore artifacts are object-specific directories named
`mvtec_<object>` containing `patchcore_params.pkl` and
`nnscorer_search_index.faiss`. For full MVTec coverage, point
`KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT` or CLI `--object-checkpoint-root` at the
root containing directories such as `mvtec_bottle`, `mvtec_capsule`, and
`mvtec_metal_nut`; KGTraceVis resolves the object-specific artifact from the
sample's object name. Lightweight Git LFS clones that contain only pointer
files are not considered usable artifacts; run `git lfs pull` for the selected
object directories before using the root.

### Official Amazon PatchCore Artifacts

The official Amazon PatchCore artifacts are object-specific, not one global
MVTec model. Each MVTec object needs its own `mvtec_<object>` directory with
real Git LFS contents:

```text
amazon_patchcore_models/
`-- IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/
    `-- models/
        |-- mvtec_bottle/
        |   |-- patchcore_params.pkl
        |   `-- nnscorer_search_index.faiss
        |-- mvtec_capsule/
        |   |-- patchcore_params.pkl
        |   `-- nnscorer_search_index.faiss
        `-- mvtec_metal_nut/
            |-- patchcore_params.pkl
            `-- nnscorer_search_index.faiss
```

Clone without smudging the full Git LFS payload, then pull only the selected
objects you need:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/amazon-science/patchcore-inspection.git
cd patchcore-inspection
git lfs install --local

# Selected objects. Adjust the run folder if using a different artifact set.
git lfs pull \
  -I "models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_bottle/**" \
  -I "models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_capsule/**"

# Or pull every official artifact tracked by the repo.
git lfs pull -I "models/**"
```

Avoid pointer-only false positives by checking that artifact files are real
binary payloads, not small text pointers:

```bash
head -n 1 models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_bottle/patchcore_params.pkl
du -h models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_bottle/*
```

If the first line starts with `version https://git-lfs.github.com/spec/v1`, run
`git lfs pull` for that object before using it. KGTraceVis also rejects
pointer-only `.pkl` and `.faiss` files during availability checks.

For batch record generation, pass the common root and let KGTraceVis resolve
the object-specific directory from each sample path:

```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

uv run python scripts/build_dataset_records.py --dataset mvtec \
  --input-root data/external/mvtec \
  --output-jsonl data/processed/records/mvtec_amazon_patchcore.jsonl \
  --model-backend amazon-patchcore \
  --object-checkpoint-root /path/to/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models \
  --threshold-config configs/mvtec_patchcore_thresholds.json \
  --device cpu \
  --overwrite
```

For paper-deadline evidence generation, KGTraceVis includes a supervised quick
calibration path that writes per-object PatchCore score/map thresholds:

```bash
uv run python scripts/calibrate_mvtec_patchcore_thresholds.py \
  --dataset-root /path/to/Defect_Spectrum \
  --artifact-root /path/to/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models \
  --output-config configs/mvtec_patchcore_thresholds.json \
  --output-csv configs/mvtec_patchcore_thresholds.csv \
  --max-good 1 \
  --max-defect-per-label 1 \
  --device cpu \
  --overwrite
```

These thresholds are explicitly supervised calibration artifacts for usable
KGTraceVis evidence. They are not unsupervised MVTec benchmark results.

To run the calibrated records through the full Evidence adapter and
`KGTracePipeline` path in one command:

```bash
uv run python scripts/run_mvtec_calibrated_pipeline.py \
  --dataset-root /path/to/Defect_Spectrum \
  --artifact-root /path/to/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models \
  --threshold-config configs/mvtec_patchcore_thresholds.json \
  --output-root runs/mvtec_calibrated_pipeline \
  --max-good 1 \
  --max-defect-per-label 1 \
  --device cpu \
  --overwrite
```

This writes producer records, generated Evidence JSON, the KGTrace summary, and
a table-ready CSV under the output root.

For FastAPI image uploads, set the PatchCore checkpoint env var to the common
root instead of one hard-coded object directory:

```bash
export KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT=/path/to/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models
```

When `model_preset=patchcore`, the API resolves the root by the uploaded
`object_name` (`bottle` -> `mvtec_bottle`, `metal_nut` -> `mvtec_metal_nut`).
The current local official Amazon PatchCore root has been downloaded for all 15
MVTec objects. A calibrated full-class smoke run using
`configs/mvtec_patchcore_thresholds.json` produced 30 records, 15/15 defect
samples predicted anomalous, 14/15 sampled good images predicted normal, and a
mean mask area ratio of about 0.058 instead of near-full-image masks.

The checked-in examples include all three scenarios plus one explicitly noisy
MVTec demo case that triggers correction candidates. The example JSON files are
observed evidence inputs only: adapters or manual demo annotations provide
object/anomaly/location/morphology/variable/log-event fields, while
`KGTracePipeline` computes entity linking, consistency, correction candidates,
and candidate/plausible RCA reasoning at runtime. The RCA stage emits aligned
`top_k_paths` and `ranked_root_causes`: generic graph reasoning derives root
causes from ranked KG paths, while scenario-aware reasoners such as native TEP
can provide both fields from native support-path logic. MVTec demo RCA source
edges are curated plausible references, and displayed paths are runtime
candidates, not real factory RCA labels.

Run tests and lint:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

Common Makefile shortcuts:

```bash
make setup
make setup-ml
make setup-cuda
make test
make examples
make dev
make real-pipeline
```

Start the maintained web-facing backend directly:

```bash
make api
```

or:

```bash
uv run python scripts/run_web_api.py
```

This starts the FastAPI service on `http://127.0.0.1:8000`.

Start the KGTraceVis workbench client:

```bash
cd web
npm install
npm run dev
```

The Vite dev server starts on `http://127.0.0.1:5173` and proxies `/api` to the
local FastAPI service. The maintained client uses Arco React components,
ECharts graph views, plain CSS tokens, and React Router routes for Home,
Analysis, KG Studio, and Experiments modules. To type-check and build the
dashboard:

```bash
cd web
npm run typecheck
npm run build
```

On a Windows CUDA workstation, install `uv` and GNU Make, then run:

```powershell
make setup-cuda
make dev
```

If Make is not available, use the PowerShell helper instead:

```powershell
.\scripts\dev_cuda_windows.ps1
```

The FastAPI upload workflow currently accepts evidence JSON, producer-record
bundles (`.json`, `.jsonl`, or `.csv`), or a raw MVTec-style image, and writes
new dashboard run artifacts under `runs/rootlens_sessions/`. Run list/detail
state is read from Postgres `analysis_runs` and related runtime tables, not
legacy session manifests. Image mode uses a selectable MVTec
anomaly-detection/localization preset. `auto` prefers
EfficientAD, then PatchCore, then the checked-in STFPM OpenVINO checkpoint.
Configure replacement
weights with `KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT` or
`KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT`; the PatchCore value may be either one
checkpoint/artifact directory or a full Amazon PatchCore root containing
`mvtec_<object>` directories. In image mode, Amazon PatchCore roots are resolved
by the uploaded `object_name`. Git LFS pointer-only directories are reported as
unavailable until the real `.pkl` and `.faiss` files are downloaded. By default,
the API also recognizes the Makefile/API asset path under
`runs/real_model_pipeline/assets/`. The optional defect field accepted by API
clients is a human prior, not a model-inferred semantic defect class.
When a MVTec preset checkpoint is missing, API clients can request its download
through the backend and then refresh the preset availability. STFPM and
PatchCore have default trusted sources; EfficientAD requires a configured
trusted source.

The RootLens dashboard initializes through `GET /api/dashboard/bootstrap`,
uploads through `POST /api/runs/upload`, reloads history through `GET /api/runs`
and `GET /api/runs/{run_id}`, and records review feedback with `POST
/api/feedback`. Run history and review feedback are persisted in Postgres; they
do not mutate the Neo4j KG or tracked KG seed CSV files.

## Unified Evidence Schema

Every dataset adapter must output the shared evidence schema. Dataset-specific
details belong inside `raw_evidence`, not in separate schema variants.

Required top-level fields:

- `case_id`
- `dataset`
- `source`
- `object`
- `anomaly_type`
- `location`
- `morphology`
- `severity`
- `confidence`
- `timestamp`
- `raw_evidence`
- `normalized_evidence`
- `kg_analysis`

The schema also reserves `human_feedback` for future review actions.

### Adapter Record Fixtures

Small model-output-style records are checked in under `data/examples/records/`.
They exercise the model-independent Evidence adapter layer without training or
downloading producers:

```bash
uv run python scripts/generate_evidence.py \
  --input data/examples/records/mvtec_records.jsonl \
  --output-jsonl outputs/mvtec_adapter_evidence.jsonl

uv run python scripts/generate_evidence.py \
  --input data/examples/records/wm811k_records.jsonl \
  --output-jsonl outputs/wm811k_adapter_evidence.jsonl
```

To run the same records end to end through `KGTracePipeline` and write generated
Evidence JSON, a provenance-rich summary, and a scoped CSV table:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/mvtec_records.jsonl \
  --dataset mvtec \
  --output-dir outputs/adapter_pipeline_v0/mvtec \
  --overwrite

uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_v0/wm811k \
  --overwrite
```

For TEP records, `scripts/run_adapter_pipeline.py` uses the single Root-KGD RCA
provider:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/processed/records/tep_rbc_subset.jsonl \
  --dataset tep \
  --output-dir outputs/adapter_pipeline_v0/tep \
  --overwrite
```

The TEP provider consumes the current Evidence variable contributions plus
dynamic window features, then populates both `top_k_paths` and
`ranked_root_causes`. Precomputed TEP_KG ranking artifacts are not part of this
runtime path, and fault-number labels are evaluation references only, not
scoring input.

To run the paper-facing TEP RCA evaluation from raw TEP CSVs:

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_raw_batch_eval_unified \
  --raw-data-dir data/raw/tep \
  --faults 1,2,6 \
  --max-runs-per-fault 2 \
  --top-k 5 \
  --overwrite
```

This dedicated evaluation command explicitly defaults to the native TEP
Root-KGD provider, rebuilds TEP producer records, runs the adapter and
`KGTracePipeline`, then writes `tep_rca_evaluation_summary.json` and
`tep_rca_evaluation_cases.csv`. Fault labels are used only for metric
calculation, not for native RCA scoring.

WM811K records keep `dataset="wafer"` and identify the adapter with
`adapter="wm811k"` or `source_dataset="wm811k"`. Adapters emit observed evidence
only; `kg_analysis` and candidate/plausible explanation paths are populated
later by `KGTracePipeline`. These path outputs are not verified process RCA
claims. The table output is `adapter_pipeline_table.csv` in the selected output
directory. The record contracts are documented in `docs/adapter_contracts.md`,
and paper-use eligibility is documented in
`docs/paper_experiment_protocol.md`.

## KG CSV Schema

Nodes:

```csv
id,name,label,scenario,aliases,description
```

Edges:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

Every edge must be traceable to a source. If a relation is uncertain, mark it as
`review_status=auto` and use a lower confidence.

Source-to-KG construction exports additional optional RCA columns for reasoning
views, including `relation_family`, propagation metadata, anchors,
`source_trust`, `rca_score`, and `rca_score_*` components. These are
explanatory/ranking metadata and do not change the required base edge contract.

## Source Registry

KG source references should be centralized in:

```text
data/kg/source_registry.csv
docs/sources/
```

KG edges should reference `source_id` values instead of vague source names.

## Development Order

Recommended v0 order:

1. `pyproject.toml` + `uv.lock`
2. README + AGENTS
3. directory structure
4. evidence schema
5. example JSON
6. minimal KG CSV files
7. Neo4j import
8. entity linker
9. consistency checker
10. path ranker
11. noise injector
12. metrics
13. FastAPI backend and future RootLens dashboard boundary
14. dataset adapters
15. experiments

Prioritize a working, reproducible v0 pipeline over completeness.
