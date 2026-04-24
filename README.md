# KGTraceVis

KGTraceVis is a research prototype for knowledge-enhanced industrial anomaly
detection and root-cause traceability.

The project converts heterogeneous anomaly outputs from images, process time
series, and wafer logs into a unified anomaly evidence JSON schema. It then uses
a source-constrained industrial knowledge graph to support entity linking,
evidence consistency scoring, noisy evidence correction, relation-weighted
root-cause path ranking, and visual analytics.

## Design Position

KGTraceVis should stay small and reproducible in v0.

The current target is:

```text
example JSON -> KG link -> consistency score -> correction -> path ranking -> demo
```

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
   evidence inspection, correction review, path comparison, and human feedback.

The interactive mode is intentionally lightweight at first. Streamlit is the v1
demo target; FastAPI or a custom front end can be added later without rewriting
the core logic.

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

Start the Streamlit demo:

```bash
uv run streamlit run src/kgtracevis/app/streamlit_app.py
```

Run tests and lint:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

Equivalent Makefile shortcuts:

```bash
make install
make test
make lint
make examples
make app
```

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
13. Streamlit demo
14. dataset adapters
15. experiments

Prioritize a working, reproducible v0 pipeline over completeness.
