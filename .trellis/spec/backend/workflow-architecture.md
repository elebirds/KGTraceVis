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

def run_source_kg_construction_workflow(
    config: SourceKGConstructionWorkflowConfig,
) -> SourceKGConstructionWorkflowResult: ...

def run_kg_construction_acceptance_smoke(
    config: KGConstructionSmokeConfig,
) -> KGConstructionSmokeResult: ...

def replay_kg_construction_reviews(
    config: ReplayKGConstructionReviewsConfig,
) -> ReplayKGConstructionReviewsResult: ...
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

#### RCA Reasoner Contract

`RcaReasoner` is the extension point for scenario-specific RCA scoring inside
the unified `KGTracePipeline`. Reasoners receive graph context and must return
aligned path and candidate outputs:

```python
def reason_root_causes(
    evidence: Evidence,
    *,
    graph: KnowledgeGraph,
    linked_entities: list[dict[str, Any]],
    top_k: int = 5,
) -> RcaReasoningResult:
    ...
```

Rules:

- The reasoner must return unified `RcaReasoningResult` objects, not a
  dataset-specific payload.
- The pipeline passes the runtime graph snapshot to scenario-aware reasoners.
- The pipeline does not wrap legacy `rank_root_causes(...)`-only providers.
- Reasoners must not construct or mutate KG data as a side effect of ranking.
- TEP-native support path search must stay scoped to `tep` and `shared` nodes
  and edges.

#### TEP Root-KGD Runtime Contract

TEP native RCA means the Root-KGD runtime provider, not an artifact bridge and
not the legacy direct-support fallback.

Signatures and entry points:

```python
def build_root_cause_reasoner() -> RcaReasoner: ...

def run_tep_rca_evaluation(
    config: TepRcaEvaluationConfig,
) -> TepRcaEvaluationOutput: ...
```

Runtime contracts:

- `build_pipeline()` attaches `TepRootKgdRcaProvider` as the single supported
  scenario-specific RCA reasoner.
- Generic adapter, upload, and evaluation callers must not expose
  `tep_rca_provider` switches. TEP RCA has no public `none/native/simple/artifact`
  mode split.
- `TepRootKgdRcaProvider` returns rankings only for TEP Evidence. For non-TEP
  Evidence it returns an empty RCA result, and `KGTracePipeline` falls back to
  the generic graph path reasoner.
- `TepRootKgdRcaProvider` loads static model assets from
  `data/kg/tep_root_kgd/`.
- Runtime scoring reads the current `Evidence` payload:
  `raw_evidence.variable_contributions`, `raw_evidence.extra.graph_contributions`,
  `raw_evidence.extra.channel_contributions`, and
  `raw_evidence.extra.root_kgd_dynamic_features`.
- Runtime scoring must not read TEP_KG per-scenario ranking outputs such as
  `baseline_root_scores.csv`, `topk_subgraphs`, `root_kgd_rankings.jsonl`, or
  `rbc_contributions.jsonl`.
- Fault numbers may appear in evaluation summaries as benchmark references,
  but must not be used as scoring inputs.
- `ranked_root_causes[*].explanation_paths` must be a subset of returned
  `top_k_paths`, so visual review and feedback IDs stay aligned.
- The provider must use the passed runtime `KnowledgeGraph` for read-only
  provenance enrichment when candidate overlay edges carry `external_edge_id`
  values matching Root-KGD static edge IDs. This enrichment may add
  `source_edge_ids`, `source_edges[*].kg_build_id`, and path-level
  `kg_build_ids`, but must not alter Root-KGD scoring or publish/review facts.

Validation:

| Condition | Behavior |
|---|---|
| TEP Evidence has no Root-KGD contributions | return empty RCA result, not artifact fallback |
| public CLI/API asks for provider mode | do not expose that option; Root-KGD is the only TEP RCA mode |
| Root-KGD asset file is missing | fail fast with the missing file name |
| non-TEP Evidence reaches Root-KGD provider | return empty RCA result |
| explanation path is not returned in `top_k_paths` | test failure; candidate paths must be reviewable |

### 5. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| CLI passes invalid workflow option | raise `ValueError` or argparse error with concrete option name |
| Workflow receives invalid Evidence JSON | let Pydantic validation surface |
| Optional model dependency is missing | fail in the producer/model workflow that explicitly needs it |
| API receives expected workflow `ValueError` | map to a structured 4xx response |
| Runtime KG provider is unavailable for an analysis path | fail with configuration guidance unless an explicit test graph was supplied |
| A workflow needs KG construction output | accept explicit paths/provider/version; do not run hidden extraction by default |
| Source-to-KG workflow receives no sources | raise `ValueError` before writing artifacts |
| Source-to-KG workflow output files already exist | raise `ValueError` unless overwrite is explicit |
| Source-to-KG API receives unsupported source shape | reject with a structured 4xx response |
| RCA reasoner is configured | pass the runtime `KnowledgeGraph` snapshot through `reason_root_causes` |
| Legacy rank-only RCA provider is passed to pipeline | unsupported; implement `reason_root_causes` |
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

Good:

```python
config = SourceKGConstructionWorkflowConfig(...)
result = run_source_kg_construction_workflow(config)
```

Bad:

```python
# FastAPI route writes KG construction CSVs directly.
export_kg_csv(nodes, edges, nodes_path=..., edges_path=...)
```

## Scenario: Document Understanding For Source KG Construction

### 1. Scope / Trigger

- Trigger: changing material extraction, `document_understanding_mode`,
  document-map artifacts, cross-chunk proposals, or review-time promotion of
  document-level claims.
- Reason: document understanding crosses API/service DTOs, LLM adapters,
  material artifacts, source-to-KG construction, review queues, publish
  snapshots, and runtime RCA overlay validation.

### 2. Signatures

Material extraction request fields:

```text
document_understanding_mode: "chunk" | "long_context" | "agentic"
document_understanding_provider: "none" | "openai" | "offline_fixture"
document_understanding_prompt_version: str
document_understanding_fixture_path: str | None
document_understanding_payload: dict | None
```

Document understanding adapter boundary:

```python
class DocumentUnderstandingClient(Protocol):
    def understand_document(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        mode: DocumentUnderstandingMode,
        step_name: str,
        prompt: str,
        response_schema: Mapping[str, Any],
        prior_steps: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any] | str: ...
```

Agentic reading uses a deterministic `DocumentReadingPlan` with chunk summaries
and per-step `selected_chunk_ids`; prompts should pass selected chunks plus the
auditable plan, not blindly pack every chunk for every step.

### 3. Contracts

- `chunk` mode is the default and must preserve current chunk IE behavior.
- `long_context` may call a configured document-understanding client; with
  provider `none`, it must produce a deterministic advisory fallback.
- `agentic` must be distinct from `long_context`: it records `agent_steps`,
  `document_reading_plan`, retrieval strategy, and selected chunk IDs.
- Document maps are advisory only. They may guide prompt context and review
  queues, but they are not DraftKG, reviewed KG, or published KG.
- Chunk IE prompts may receive only chunk-scoped map items. Items without
  `chunk_ids` must not be injected into every chunk prompt.
- Cross-chunk proposals must preserve source/document scenario; do not default
  every proposal to `shared`.
- Accepting a `cross_chunk_relation_candidate` may stage a reviewed edge only
  after explicit review. Build-time processing must never create or publish the
  edge.
- Optional reviewed RCA staging policy must be explicit in
  `review_acceptance_policy` or `rca_policy`, capped, relation/family
  whitelisted, and applied only at review accept time.

### 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| `chunk` mode includes DU provider or fixture | reject at request validation |
| DU fixture path and payload are both supplied | reject at request validation |
| OpenAI DU provider lacks API key | fail only when that provider is used |
| DU client returns invalid JSON/schema | raise `ValueError` naming `source_id:step_name` |
| map item has no `chunk_ids` | omit it from chunk-specific prompt context |
| cross-chunk proposal lacks allowed relation/head/tail/2 spans | write rejected proposal row; no review item |
| valid cross-chunk proposal before review | review queue item only; no `edges.csv` row |
| accepted cross-chunk proposal endpoint missing from nodes | reject staging with missing node IDs |
| RCA opt-in policy requests unsupported relation/family | stage reviewed edge with conservative default RCA fields and audit `ignored` |
| RCA opt-in score/priority/source_trust exceed caps | cap values and audit applied caps |

### 5. Good/Base/Bad Cases

- Good: `agentic` selects representative chunks for the outline step, records
  selected chunk IDs, and later steps receive prior step outputs.
- Base: `long_context` with provider `none` writes deterministic map/context
  artifacts and keeps existing chunk IE grounding.
- Bad: a document-map alias without `chunk_ids` appears in every chunk prompt.
- Bad: a TEP cross-chunk proposal enters review as `scenario=shared`.
- Bad: accepting a cross-chunk proposal lets caller-supplied
  `proposed_payload` rewrite relation/confidence/validation fields.

### 6. Tests Required

- Request DTO validation for DU provider/fixture combinations.
- Fake DU client test proving `long_context` calls the client and writes
  client-derived map content.
- Agentic test proving multiple named steps, prior-step counts, reading-plan
  metadata, and selected chunk prompts that do not include all chunk text.
- Chunk prompt context test proving unscoped document-map terms do not leak.
- Cross-chunk proposal tests for rejected invalid proposals, valid review-only
  proposals, preserved scenario, and no build-time publication.
- Review workflow tests for default conservative staging, capped RCA opt-in,
  unsupported opt-in ignored, duplicate edge rejection, and publish snapshot
  refresh after accept.

### 7. Wrong vs Correct

Wrong:

```python
prompt = build_document_understanding_prompt(document, all_chunks, step_name="outline")
```

Correct:

```python
plan = build_document_reading_plan(document, chunks)
step_plan = plan.step_for("outline")
prompt = build_document_understanding_prompt(
    document,
    _chunks_for_step(chunks, step_plan),
    step_name="outline",
    reading_plan=plan,
    step_plan=step_plan,
)
```

Wrong:

```python
record["scenario"] = "shared"
```

Correct:

```python
record["scenario"] = proposal.get("scenario") or document_map["scenario"] or source.scenario
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

For source-to-KG construction workflow changes:

```bash
uv run --extra dev pytest tests/test_source_kg_construction_workflow.py \
  tests/test_kg_construction_pipeline.py \
  tests/test_kg_studio.py \
  tests/test_service_api.py
uv run --extra dev ruff check src/kgtracevis/workflows/source_kg_construction.py \
  src/kgtracevis/service/kg_construction.py scripts/build_source_kg.py
uv run --extra dev mypy src tests scripts
```
