# Backend Workflow Refactor Architecture

This document defines the target backend structure for turning KGTraceVis from a
research-script prototype into a maintainable analysis system.

KGTraceVis should not be refactored into a traditional MVC backend. The core
product is an evidence-to-KG-analysis workflow, not a CRUD model rendered by a
controller and view. The target architecture is a light use-case/workflow layer
between API/CLI entry points and reusable domain modules.

## Current Problem

The reusable analysis core is already reasonably well separated:

```text
Evidence
-> KGTracePipeline
-> entity linking
-> consistency checking
-> correction generation
-> path ranking
-> AnalysisResult
```

The pressure point is orchestration. Some scripts and service helpers currently
own multi-step business flows such as:

- uploaded file persistence,
- model backend selection,
- producer record generation,
- adapter-to-Evidence conversion,
- pipeline execution,
- artifact writing,
- workflow step assembly,
- review target construction,
- run/session storage.

That makes CLI scripts, FastAPI handlers, and experiments drift into parallel
implementations of the same workflow.

## Target Layering

```text
API / CLI / experiment entry points
  -> workflows / use cases
    -> producers, adapters, core pipeline, KG construction, metrics
      -> infrastructure repositories and artifact stores
```

Recommended package layout:

```text
src/kgtracevis/
├── core/            # KGTracePipeline and result contracts
├── schema/          # Evidence and API/domain schemas
├── producers/       # model-aware record producers
├── adapters/        # model-independent record -> Evidence conversion
├── kg/              # runtime KG access, linking, consistency, ranking
├── kg_construction/ # source-constrained KG draft/export helpers
├── workflows/       # reusable application/use-case orchestration
├── service/         # FastAPI routes and HTTP request/response adaptation
├── feedback/        # feedback records and confidence updates
├── metrics/         # standalone metric functions
└── noise/           # reproducible noise injection
```

`workflows/` is the new boundary. It should hold complete reusable use cases,
not HTTP-specific code and not algorithm internals.

## Workflow Responsibilities

Workflow modules may:

- validate workflow-level options;
- select producer/adaptor/pipeline components;
- coordinate multiple reusable modules;
- write structured artifacts under caller-provided output directories;
- return Pydantic/dataclass result objects usable by API, scripts, and tests;
- preserve claim-boundary language for candidate/plausible explanations.

Workflow modules must not:

- define KG industrial facts;
- mutate reviewed KG edges;
- embed FastAPI request/response classes;
- print during normal library execution;
- depend on scripts or frontend state;
- change Evidence, KG CSV, or path-ranking contracts ad hoc.

## Proposed Workflow Modules

```text
src/kgtracevis/workflows/
├── evidence_analysis.py      # Evidence -> AnalysisResult/envelope
├── records_pipeline.py       # records -> Evidence -> analysis table/summary
├── dataset_records.py        # raw/model inputs -> producer records
├── image_upload_pipeline.py  # image upload -> producer record -> analysis
├── real_model_pipeline.py    # public model/input smoke pipeline
├── noise_experiment.py       # deterministic noise experiment orchestration
└── run_manifest.py           # run detail, workflow steps, artifacts envelope
```

The list is a migration target, not a mandate to create every file immediately.
Each extraction should keep public CLI/API behavior stable.

## Service Boundary

FastAPI code under `src/kgtracevis/service/` should be thin:

```text
HTTP request
-> request model / form parsing
-> workflow call
-> HTTP error mapping
-> response serialization
```

Service modules may compose API envelopes, but reusable business behavior should
move into `workflows/` once scripts or tests also need it.

## Script Boundary

Scripts under `scripts/` should be CLI clients:

```text
argparse
-> workflow config/result
-> concise print
```

They should not own reusable predictor factories, full analysis orchestration,
artifact schema generation, metric aggregation, or KG construction logic.

## Experiment Boundary

Experiment modules may own paper/report-specific summaries, but they should call
the same workflows used by scripts and the API. Experiment code should not
duplicate producer-to-Evidence-to-analysis behavior.

## Reusable KG Pipeline Integration

A separate reusable KG pipeline is under active development. This refactor must
reserve space for it without implementing it here.

The integration point should be an explicit provider boundary:

```text
workflow
-> KG provider / KG pipeline facade
-> KG snapshot or runtime repository
-> KGTracePipeline analysis
```

Expected responsibilities of the external KG pipeline:

- source registration and loading;
- source-constrained candidate entity/triple generation;
- confidence and review metadata preservation;
- draft/review/export lifecycle;
- runtime KG version selection;
- Neo4j import/export or query-ready graph snapshots.

Expected responsibilities of this backend workflow refactor:

- accept an explicit KG runtime/provider when needed;
- keep scenario scoping (`shared + dataset`) intact;
- keep Evidence analysis independent from KG construction internals;
- expose enough provenance in workflow results for review and visual analytics;
- avoid hard-coding a single KG construction implementation.

Do not couple `KGTracePipeline` directly to a construction pipeline. It should
consume a `KnowledgeGraph`, Neo4j-backed snapshot repository, or future provider
adapter with the same scenario-scoped semantics.

## Migration Phases

### Phase 1: Thin Scripts

Move reusable script logic into `src/kgtracevis/workflows/` while preserving CLI
arguments and printed summaries.

Good first candidates:

- `scripts/build_dataset_records.py`
- `scripts/run_real_model_pipeline.py`
- `scripts/run_noise_experiment.py`

### Phase 2: Split Run Service

Break `src/kgtracevis/service/runs.py` into smaller units:

- run store / manifest loading,
- upload dispatch,
- model image upload workflow,
- records upload workflow,
- artifact helpers,
- review target builders,
- visual evidence enrichment.

### Phase 3: Runtime Storage Boundary

Move filesystem/JSON run persistence behind a store interface that can later use
Postgres as the default runtime state backend while retaining file artifacts for
large uploads and generated images.

### Phase 4: KG Provider Boundary

Add a small explicit interface for selecting KG runtime snapshots or versions.
This should adapt the reusable KG pipeline when it is ready, without changing
the Evidence analysis contract.

## Compatibility Rules

- Public CLI flags should remain backward-compatible during extraction.
- API response fields should not be renamed as part of workflow refactoring.
- Evidence JSON, KG CSV, and path-ranking result contracts are unchanged.
- MVTec RCA language must remain candidate/plausible unless reviewed evidence
  supports stronger claims.
- Reusable library functions should return structured results instead of
  printing.

## Quality Gate

For each refactor slice, run focused tests covering the moved behavior. Before
submitting a broader backend refactor, run:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
uv run python scripts/run_examples.py
```

If Neo4j runtime behavior changes, also run:

```bash
uv run python scripts/import_kg.py
uv run python scripts/run_examples.py --with-neo4j
```
