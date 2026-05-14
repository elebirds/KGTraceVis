# implement: wire TEP RCA provider selection

## Goal

把已经实现的 `TepNativeRcaProvider` 从“手动传入 pipeline 才能用”推进到现有运行入口可配置使用。目标是让 scripts / adapter pipeline / service upload 仍然走统一 `KGTracePipeline`，但可以明确选择 TEP RCA provider：

```text
none/default -> path projection fallback
native       -> TepNativeRcaProvider
artifact     -> TepRcaArtifactProvider
```

## What I Already Know

* `RootCauseProvider` 和 `ranked_root_causes` 已经是统一主干。
* `TepRcaArtifactProvider` 能读取外部 Root-KGD/TEP_KG 风格 artifacts。
* `TepNativeRcaProvider` 能从 TEP Evidence + KGTraceVis `KnowledgeGraph` 计算原生 RCA ranking。
* 当前入口大多直接构造 `KGTracePipeline()`，所以 native provider 还没有默认/显式接线入口。
* 本任务不改变 KG 建设，不引入新 route2。

## Scope

Add a small provider-selection layer that can be reused by CLI/service/workflows.

Candidate shape:

```python
def build_root_cause_provider(config: ...) -> RootCauseProvider | None:
    ...

def build_pipeline(..., tep_rca_provider: Literal["none", "native", "artifact"] = "none") -> KGTracePipeline:
    ...
```

Exact module/name can follow existing code patterns.

## Requirements

* [x] Add a reusable provider selection helper under `src/kgtracevis/`.
* [x] Support at least:
  * `none` / default: no explicit provider, existing fallback behavior.
  * `native`: use `TepNativeRcaProvider`.
  * `artifact`: use `TepRcaArtifactProvider` and require artifact path/config.
* [x] Wire provider selection into `run_adapter_pipeline` and `scripts/run_adapter_pipeline.py`.
* [x] Wire provider selection into `scripts/run_examples.py` for local smoke tests.
* [x] Wire provider selection into service upload path in a conservative way, likely via optional parameter/env/config helper, without breaking existing API tests.
* [x] Preserve existing behavior when no provider option is passed.
* [x] Add tests for:
  * selection helper,
  * adapter pipeline native provider path,
  * CLI args or script helper behavior,
  * error when artifact provider is requested without artifact path.

## Non-Goals

* Do not make native provider mandatory.
* Do not make TEP artifact bridge the default.
* Do not rebuild KG CSVs.
* Do not change frontend UI in this slice unless backend API already exposes the needed option trivially.
* Do not introduce a separate TEP route.

## Acceptance Criteria

* [x] Existing tests still pass with default behavior.
* [x] Running adapter pipeline with native provider produces TEP `ranked_root_causes` when KG support exists.
* [x] Running examples can be configured to use native provider.
* [x] Artifact provider selection validates missing artifact path.
* [x] Service upload helpers can receive or resolve provider selection without changing current callers.

## Verification Plan

* `uv run --extra dev pytest tests/test_root_cause_provider_selection.py tests/test_tep_native_rca_provider.py tests/test_tep_rca_bridge.py tests/test_adapter_pipeline.py tests/test_run_examples_script.py tests/test_service_api.py` -> 53 passed.
* `uv run python scripts/run_examples.py` -> passed.
* Scoped lint/typecheck -> passed.
* Full `uv run --extra dev pytest` currently blocked by unrelated source-to-KG task syntax error in `scripts/build_source_kg.py`; focused provider-selection tests pass.

## Implemented Notes

* Added `root_cause_provider_selection.py` with shared `none` / `native` /
  `artifact` config and environment fallback support.
* `artifact` selection now fails fast unless it can resolve a ranking artifact.
* CLI flags were added to `scripts/run_examples.py` and
  `scripts/run_adapter_pipeline.py`.
* Service upload path accepts optional TEP RCA provider parameters while
  preserving default callers.
