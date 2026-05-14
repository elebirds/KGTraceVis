# implement: TEP native RCA provider

## Goal

把 TEP RCA 从“只消费外部 artifact 的 bridge”推进到 KGTraceVis 原生 RCA provider 的第一版：在统一 `RootCauseProvider` 协议下，直接从 TEP evidence、KGTraceVis `KnowledgeGraph`、变量贡献信息和图关系计算 `ranked_root_causes`。

这一步不改变主干 pipeline；仍然是：

```text
adapter evidence -> KGTracePipeline -> linked evidence / consistency / top_k_paths -> ranked_root_causes
```

## What I Already Know

* 上一任务已经完成统一 RCA 合约：
  * `AnalysisResult.ranked_root_causes`
  * `RootCauseProvider`
  * `TepRcaArtifactProvider`
  * Postgres/service/dashboard payload 透传
  * `root_cause_candidate` feedback target
* 用户明确要求主干统一，TEP 不应作为 `route2` 长期存在。
* 另一个 Agent 正在统一 KG 建设，本任务不负责构建 TEP KG CSV；只消费已有/运行时 KG。
* TEP evidence 已能携带 `fault_number`、`simulation_run`、变量列表、变量贡献等 metadata。
* 当前第一版可以先实现轻量 Root-KGD-style scorer，不追求完整复刻 TEP_KG 的所有实验模块。

## Scope

Implement a new KGTraceVis-native provider, tentatively:

```python
TepNativeRcaProvider
```

It should:

* implement `RootCauseProvider.rank_root_causes(...)`;
* only activate for `Evidence.dataset == "tep"`;
* consume current `KnowledgeGraph` plus TEP evidence variable/contribution metadata;
* combine:
  * evidence variable match,
  * KG relation/path support,
  * edge confidence,
  * short path preference,
  * optional `top_k_paths` fallback context;
* emit unified `RankedRootCause` objects with stable IDs, supporting paths/edges/evidence, score details, and `scoring_method` distinct from artifact bridge.

## Non-Goals

* Do not rewrite KG construction.
* Do not add unsupported TEP causal facts.
* Do not remove `TepRcaArtifactProvider`; it remains useful for comparing external Root-KGD artifacts.
* Do not introduce a separate route/service path.
* Do not require Neo4j to run unit tests; tests should use in-memory `KnowledgeGraph`.

## Requirements

* [x] Add a native TEP provider module or extend the existing TEP RCA workflow module cleanly.
* [x] Provider can be configured with a `KnowledgeGraph` or receive graph context in a way compatible with `KGTracePipeline`.
* [x] If needed, extend `RootCauseProvider` protocol conservatively so providers can access the runtime graph without breaking existing providers.
* [x] Extract TEP variable evidence from normalized fields, raw `extra`, observations, and contribution maps.
* [x] Score candidate root causes using KG paths/edges rather than only artifact rows.
* [x] Return `RankedRootCause` with:
  * stable `ranking_id`,
  * `candidate_id`,
  * `rank`,
  * `score`,
  * `confidence`,
  * `evidence_match`,
  * `explanation_paths`,
  * `supporting_edges`,
  * `supporting_evidence`,
  * `scoring_method`,
  * `scoring_details`.
* [x] Keep `top_k_paths` compatibility behavior intact.
* [x] Add focused tests for:
  * variable contribution extraction,
  * KG-backed candidate ranking,
  * no ranking for non-TEP evidence,
  * pipeline integration through `KGTracePipeline(root_cause_provider=...)`.

## Acceptance Criteria

* [x] TEP native provider returns non-empty `ranked_root_causes` for a controlled in-memory TEP KG fixture.
* [x] Candidate order changes when variable contribution/evidence match changes.
* [x] Provider does not attach candidates without KG support.
* [x] Existing artifact bridge tests still pass.
* [x] Full tests, lint, and typecheck pass or any skipped checks are explicitly explained.

## Design Notes

Native scoring should be conservative and explainable. A suitable v0 formula is:

```text
score = alpha * evidence_match + beta * graph_confidence + delta * propagation_support - gamma * path_length
```

Where:

* `evidence_match` comes from observed TEP variables and contribution weights.
* `graph_confidence` aggregates source-constrained KG edge confidence.
* `propagation_support` rewards candidate paths that connect to multiple affected variables.
* `path_length` penalizes overly long explanations.

The exact weights can be config defaults. The important part is that the output is traceable and every supporting edge comes from KGTraceVis KG data.

## Risks

* Current TEP KG seed files may still be sparse while the KG-building Agent works.
* Relation names may differ between imported TEP KG and current path ranking conventions.
* Full Root-KGD may need richer graph semantics than the first native provider can provide.

## Verification Plan

* `uv run --extra dev pytest tests/test_tep_native_rca_provider.py tests/test_tep_rca_bridge.py tests/test_pipeline.py`
* `uv run --extra dev pytest` -> 219 passed.
* `uv run --extra dev ruff check .` -> passed.
* `uv run --extra dev mypy src tests scripts` -> passed.
* `uv run python scripts/run_examples.py` -> passed.

## Implemented Notes

* `TepNativeRcaProvider` ranks TEP candidates with `scoring_method="tep_native_kg"`.
* `extract_tep_variable_evidence` normalizes variables from raw evidence,
  normalized evidence, observations, and contribution maps.
* `KGTracePipeline` now passes runtime graph context to graph-aware
  `RootCauseProvider` implementations while preserving compatibility for
  legacy providers that do not accept `graph`.
* Native TEP support-path traversal is constrained to `tep` and `shared` KG
  nodes/edges.
