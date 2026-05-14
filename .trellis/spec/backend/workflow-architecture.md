# Workflow Architecture Guidelines

KGTraceVis backend code should follow a workflow/use-case architecture rather
than a traditional MVC split. API routes, scripts, and experiments are clients
of reusable workflows.

## Scenario: Backend Workflow Refactor

### 1. Scope / Trigger

Use this guideline when adding or changing:

- script orchestration under `scripts/`,
- FastAPI service handlers under `src/kgtracevis/service/`,
- multi-step producer/adapter/pipeline flows,
- run/session/artifact assembly,
- experiment orchestration that could be reused by API or CLI,
- integration boundaries for KG construction or runtime KG providers.

### 2. Signatures And Dependency Direction

```text
scripts/        -> src/kgtracevis/workflows/ -> src/kgtracevis/{core,kg,...}
service/        -> src/kgtracevis/workflows/ -> src/kgtracevis/{core,kg,...}
experiments/    -> src/kgtracevis/workflows/ -> src/kgtracevis/{core,kg,...}
workflows/      -> no dependency on scripts, FastAPI route objects, or frontend state
```

`workflows/` may depend on producers, adapters, `KGTracePipeline`, metrics,
noise helpers, KG construction helpers, and storage/repository helpers.

Workflow modules should expose one config object, one result object, and one
verb-style entry point:

```python
@dataclass(frozen=True)
class SomeWorkflowConfig:
    ...

@dataclass(frozen=True)
class SomeWorkflowResult:
    output_path: Path
    summary: dict[str, Any]

def run_some_workflow(config: SomeWorkflowConfig) -> SomeWorkflowResult:
    ...
```

Current workflow signatures include:

```python
def build_dataset_records(
    config: DatasetRecordBuildConfig,
) -> DatasetRecordBuildResult: ...

def run_noise_experiment(
    config: NoiseExperimentConfig | None = None,
    *,
    pipeline: NoiseExperimentPipeline | None = None,
) -> NoiseExperimentResult: ...

def run_real_model_pipeline(
    config: RealModelPipelineConfig,
) -> RealModelPipelineResult: ...
```

CLI modules may re-export moved helper functions briefly for backward
compatibility, but new imports should target `kgtracevis.workflows.*`.

### 3. Contracts

- Scripts parse CLI arguments, call workflows, and print concise summaries.
- FastAPI routes parse HTTP requests, call workflows or service handlers, map
  expected errors to HTTP responses, and serialize structured results.
- Workflow functions return structured dataclasses or Pydantic models.
- Workflow functions do not print during normal execution.
- Workflow modules must preserve Evidence JSON, KG CSV, and path result
  contracts unless a task explicitly changes those contracts and updates docs.
- Workflow modules must preserve candidate/plausible claim boundaries for KG
  explanations.
- Reusable model backend selection belongs under `producers/` or `workflows/`,
  not only in scripts.

### 4. Reusable KG Pipeline Boundary

Reusable KG construction/runtime pipeline work should be integrated through a
provider/facade boundary. Do not make analysis workflows depend directly on KG
construction internals.

Allowed analysis inputs:

- explicit `KnowledgeGraph`,
- `KGSnapshotRepository`-compatible runtime repository,
- future KG provider adapter that returns scenario-scoped snapshots or runtime
  repository handles.

Rules:

- Dataset analysis must use the selected dataset plus `shared`.
- Construction pipelines own source loading, candidate extraction, review
  metadata, and KG version/export lifecycle.
- `KGTracePipeline` owns case-level reasoning over validated Evidence.
- Do not implement KG construction pipeline behavior as a side effect of an
  Evidence analysis workflow.

#### RootCauseProvider Graph Context Contract

`RootCauseProvider` is the extension point for scenario-specific RCA scoring
inside the unified `KGTracePipeline`. Providers may be graph-aware:

```python
def rank_root_causes(
    evidence: Evidence,
    *,
    graph: KnowledgeGraph | None = None,
    top_k: int = 5,
    top_k_paths: list[dict[str, Any]] | None = None,
) -> list[RankedRootCause]:
    ...
```

Rules:

- The provider must return unified `RankedRootCause` objects, not a
  dataset-specific payload.
- The pipeline may pass the runtime graph snapshot to graph-aware providers.
- The pipeline must remain compatible with older providers that do not accept
  `graph`; use signature detection rather than unconditionally passing a new
  keyword.
- Providers must not construct or mutate KG data as a side effect of ranking.
- TEP-native support path search must stay scoped to `tep` and `shared` nodes
  and edges.

### 5. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| CLI passes invalid workflow option | raise `ValueError` or argparse error with concrete option name |
| Workflow receives invalid Evidence JSON | let Pydantic validation surface |
| Optional model dependency is missing | fail in the producer/model workflow that explicitly needs it |
| API receives expected workflow `ValueError` | map to a structured 4xx response |
| Runtime KG provider is unavailable for an analysis path | fail with configuration guidance unless an explicit test graph was supplied |
| A workflow needs KG construction output | accept explicit paths/provider/version; do not run hidden extraction by default |
| Root-cause provider accepts `graph` | pass the runtime `KnowledgeGraph` snapshot |
| Root-cause provider lacks `graph` parameter | call it with the legacy provider signature |
| Native TEP provider sees non-TEP edges in a mixed graph | ignore them for TEP support-path ranking |

### 6. Good/Base/Bad Cases

Good:

```python
config = DatasetRecordBuildConfig(...)
result = build_dataset_records(config)
print(json.dumps(result.summary, indent=2))
```

Base:

```python
detail = create_run_from_upload(..., pipeline=KGTracePipeline(graph=test_graph))
```

Bad:

```python
# scripts/build_dataset_records.py owns reusable predictor factories forever.
def build_mvtec_predictor(...):
    ...
```

Bad:

```python
# FastAPI route runs KG source extraction as an implicit side effect of analysis.
analysis = analyze_and_rebuild_kg(request.evidence)
```

### 7. Tests Required

For each extraction:

- keep or add tests for the reusable workflow function;
- keep at least one CLI smoke/contract test when a script is thinned;
- verify output shape is unchanged for existing callers;
- run focused tests for moved behavior before broad test suites.

Recommended focused commands depend on the slice. For dataset record workflows:

```bash
uv run --extra dev pytest tests/test_record_producers.py
uv run --extra dev ruff check src/kgtracevis/workflows scripts/build_dataset_records.py
```

For current script-to-workflow extractions:

```bash
uv run --extra dev pytest tests/test_record_producers.py \
  tests/test_noise_experiment_workflow.py \
  tests/test_real_model_pipeline_workflow.py
uv run --extra dev ruff check src/kgtracevis/workflows scripts
uv run --extra dev mypy src tests scripts
```
