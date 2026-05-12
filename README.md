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
example JSON -> KG link -> consistency score -> correction -> path ranking -> demo
```

The current paper-facing adapter milestone uses the same runtime pipeline but
starts one step earlier:

```text
producer-output records -> Evidence adapters -> Evidence JSON -> KGTracePipeline
-> candidate/plausible explanation paths
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
The app is also a client.
The reusable pipeline is the product.
```

## Usage Modes

KGTraceVis supports two usage modes:

1. Batch / script mode:
   KG construction, evidence validation, noise experiments, path ranking, and
   metric evaluation.
2. Interactive visual analytics mode:
   evidence inspection, correction review, path comparison, and human feedback
   in the FastAPI + React web system. The web UI also supports uploading
   producer-record bundles or evidence JSON to run the pipeline and inspect
   step-by-step outputs.

The web system is now the primary interactive shell. Streamlit remains
available as a lightweight legacy demo for quick inspection.

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
│       ├── service/
│       └── app/
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
- Tennessee Eastman Process: `data/external/tep/`
- Wafer data: `data/external/wafer/`

Use this convention:

```text
data/external/     original datasets, not tracked
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
```

## Common Commands

Validate example evidence:

```bash
uv run python scripts/run_examples.py
```

Build KG CSV files:

```bash
uv run python scripts/build_kg.py
```

Import KG into Neo4j:

```bash
uv run python scripts/import_kg.py
```

Run noise experiment:

```bash
uv run python scripts/run_noise_experiment.py
```

Run KG QA and the consolidated v0 suite:

```bash
uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json
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
```

Use `--model-backend fake` for checkpoint-free smoke runs. Anomalib is imported
only for `anomalib-engine`, `anomalib-torch`, or `anomalib-openvino`; sklearn
joblib/pickle checkpoints must be trusted local files. The public WM811K ResNet
asset is a defect-pattern classifier over the labeled WM811K patterns only; it
does not provide verified root-cause labels or a normal-wafer detector.
`--include-wm811k-data` downloads the public Hugging Face dataset table
`lslattery/wafer-defect-detection` / `test.pkl` into
`runs/real_model_pipeline/assets/wm811k/input_tables/`; override it with
`--wm811k-input-repo`, `--wm811k-input-file`, and `--wm811k-input-repo-type`.
The downloader stores trusted public model assets under
`runs/real_model_pipeline/assets/`, including the default MVTec STFPM OpenVINO
checkpoint used by web image mode and a default capsule PatchCore Lightning
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

For Web/API image uploads, set the PatchCore checkpoint env var to the common
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

Start the Streamlit demo:

```bash
uv run streamlit run src/kgtracevis/app/streamlit_app.py
```

The checked-in examples include all three scenarios plus one explicitly noisy
MVTec demo case that triggers correction candidates. The example JSON files are
observed evidence inputs only: adapters or manual demo annotations provide
object/anomaly/location/morphology/variable/log-event fields, while
`KGTracePipeline` computes entity linking, consistency, correction candidates,
and candidate/plausible RCA path ranking at runtime. MVTec demo RCA source
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
make check-web
make dev
make real-pipeline
```

Start the web API directly:

```bash
make api
```

Start the React frontend directly:

```bash
make web
```

The frontend proxies `/api` requests to `http://127.0.0.1:8000`, so keep the
API process running while using the browser UI.

On a Windows CUDA workstation, install `uv`, Node.js, and GNU Make, then run:

```powershell
make setup-cuda
make dev
```

If Make is not available, use the PowerShell helper instead:

```powershell
.\scripts\dev_cuda_windows.ps1
```

The upload workflow currently accepts evidence JSON, producer-record bundles
(`.json`, `.jsonl`, or `.csv`), or a raw MVTec-style image, and writes run
artifacts under `runs/web_sessions/`. Image mode uses a selectable MVTec
anomaly-detection/localization preset. `auto` prefers EfficientAD, then
PatchCore, then the checked-in STFPM OpenVINO checkpoint. Configure replacement
weights with `KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT` or
`KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT`; the PatchCore value may be either one
checkpoint/artifact directory or a full Amazon PatchCore root containing
`mvtec_<object>` directories. In image mode, Amazon PatchCore roots are resolved
by the uploaded `object_name`. Git LFS pointer-only directories are reported as
unavailable until the real `.pkl` and `.faiss` files are downloaded. By default,
the web API also recognizes the Makefile/API asset path under
`runs/real_model_pipeline/assets/`. The optional defect field in the UI is a
human prior, not a model-inferred semantic defect class.
When a MVTec preset checkpoint is missing, the web UI can request its download
through the API and then refresh the preset availability. STFPM and PatchCore
have default trusted sources; EfficientAD requires a configured trusted source.

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
13. Web system / legacy Streamlit demo
14. dataset adapters
15. experiments

Prioritize a working, reproducible v0 pipeline over completeness.
