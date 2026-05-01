# Directory Structure

KGTraceVis is a single uv-managed Python package. Keep reusable behavior under
`src/kgtracevis/`; scripts, notebooks, Streamlit, and services are clients.

## Package Layout

```text
src/kgtracevis/
├── core/              # reusable pipeline facade and result models
├── schema/            # Pydantic evidence schema and validators
├── adapters/          # dataset-to-evidence adapters
├── kg_construction/   # source-constrained KG extraction/export helpers
├── kg/                # KG loading, linking, consistency, correction, ranking
├── mask/              # mask-derived feature helpers
├── noise/             # reproducible field-level noise injection
├── metrics/           # standalone metric functions
├── viz/               # graph/plot export helpers
├── feedback/          # feedback records and confidence updates
├── service/           # future API handlers
└── app/               # Streamlit demo client
```

Examples:

- `src/kgtracevis/core/pipeline.py` wires reusable analysis modules.
- `src/kgtracevis/kg/graph.py` loads CSV KG files into an in-memory graph.
- `scripts/run_examples.py` validates examples and calls `KGTracePipeline`.

## Top-Level Directories

Allowed top-level project directories:

```text
configs/
src/
scripts/
data/
runs/
outputs/
artifacts/
notebooks/
docs/
paper/
tests/
```

Do not add new top-level directories unless the project scope truly changes.
Tooling directories such as `.trellis/`, `.agents/`, `.codex/`, `.claude/`,
`.cursor/`, and `.opencode/` are Trellis/platform scaffolding, not KGTraceVis
application structure.

## Dependency Direction

Keep dependency flow one-way:

```text
scripts/        -> src/kgtracevis/
app/service     -> src/kgtracevis/
notebooks/      -> src/kgtracevis/
src/kgtracevis/ -> no dependency on scripts/notebooks/app UI state
```

Reusable logic must not live in scripts, Streamlit pages, notebooks, or service
handlers. Those entry points may parse arguments, load config, call the core
pipeline, and save outputs.

## Data And KG Files

Small curated examples are tracked:

- `data/examples/*.json`
- `data/kg/nodes.csv`
- `data/kg/edges.csv`
- `data/kg/*_nodes.csv`
- `data/kg/*_edges.csv`
- `data/kg/*_reference.csv`

Large datasets, generated predictions, experiment runs, and derived outputs stay
under ignored paths such as `data/external/`, `data/interim/`,
`data/processed/`, `runs/`, `outputs/`, or `artifacts/`.

## Module Conventions

- New reusable analysis code goes under the closest `src/kgtracevis/<module>/`.
- Tests mirror behavior under `tests/test_<module>.py`.
- Public functions should have short docstrings.
- Use type hints where practical.
- Prefer small deterministic functions over hidden global state.

## Wrong vs Correct

Wrong:

```python
# scripts/run_noise_experiment.py
def inject_noise(evidence):
    ...
```

Correct:

```python
# src/kgtracevis/noise/noise_injector.py
def inject_noise(evidence: Evidence, seed: int) -> Evidence:
    ...
```

Then call that function from `scripts/run_noise_experiment.py`.
