# implement: unified RCA reasoning contract

## Goal

Introduce a shared RCA reasoning contract so KGTracePipeline produces aligned `top_k_paths` and `ranked_root_causes` from the same scenario-aware reasoner. This fixes the current TEP native mismatch where ranked root causes come from `TepNativeRcaProvider` while paths still come from the generic path ranker.

## What I Already Know

* `KGTracePipeline` is the single analysis entry point and must remain so.
* Dataset adapters must stay evidence-only and must not emit root causes.
* Existing `RootCauseProvider` implementations should keep working where possible.
* TEP native RCA must use TEP variable contributions plus KG support paths, scoped to `tep`/`shared`, and must not use `fault_number` labels for scoring.
* Output fields stay unchanged: `AnalysisResult.top_k_paths` and `AnalysisResult.ranked_root_causes`.
* Dirty TEP KG CSV and test changes exist and must not be reverted or overwritten.

## Requirements

* Document the shared RCA reasoner contract before implementation.
* Add a reusable reasoning result/contract that returns both `top_k_paths` and `ranked_root_causes`.
* Add a generic graph-path reasoner that wraps existing path ranking and root-cause fallback behavior.
* Adapt TEP native RCA to return unified reasoning output from the same selected support-path logic.
* Keep legacy `rank_root_causes` provider behavior as a compatibility shim where feasible.
* Update provider/pipeline selection so native TEP selects unified behavior while artifact providers remain supported.
* Add focused tests for TEP path/root-cause alignment and legacy provider compatibility.

## Acceptance Criteria

* [ ] TEP native pipeline output has `top_k_paths` aligned with the first ranked root cause's explanation/support paths.
* [ ] TEP native `ranked_root_causes[*].scoring_method` remains `tep_native_kg`.
* [ ] Generic MVTec/Wafer behavior still uses graph path ranking.
* [ ] Existing root cause providers that only implement `rank_root_causes` remain usable.
* [ ] Focused tests pass.

## Definition of Done

* Docs updated for the architecture change.
* Tests added or updated for changed RCA behavior.
* Focused pytest and ruff checks run where feasible.
* Changed files and residual risks summarized.

## Out of Scope

* Do not change KG CSV facts unless absolutely required.
* Do not make adapters emit root causes.
* Do not introduce a new top-level app workflow or dataset-specific evidence schema.

## Technical Notes

* Suggested files: `docs/project_design.md`, `README.md`, `docs/backend_workflow_refactor.md`, `src/kgtracevis/core/pipeline.py`, `src/kgtracevis/core/result.py`, `src/kgtracevis/workflows/tep_rca.py`, `src/kgtracevis/workflows/root_cause_provider_selection.py`, `tests/test_tep_native_rca_provider.py`, `tests/test_pipeline.py`.
