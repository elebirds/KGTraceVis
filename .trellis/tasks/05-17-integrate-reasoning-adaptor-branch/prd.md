# brainstorm: integrate reasoning adaptor branch

## Goal

Integrate the useful reasoning adaptor work from `codex/reasoning_adaptor` onto the current `codex/kg-generation-pipeline-refactor` backend line without reverting the KG generation pipeline refactor or importing temporary/generated artifacts.

## What I Already Know

* Current integration branch is `codex/integrate-reasoning-adaptor`, created from `codex/kg-generation-pipeline-refactor`.
* `codex/reasoning_adaptor` contains one large commit after common ancestor `b8ad05c`.
* Direct merge is unsafe: dry-run conflict analysis showed conflicts in service API, KG material/construction services, core RCA/result/path ranking code, docs, and tests.
* The frontend branch contains many non-frontend changes and generated `tmp*` artifacts; it should be treated as a patch source rather than a merge base.
* Backend refactor branch is the source of truth for KG generation pipeline architecture.

## Assumptions (Temporary)

* Preserve all source KG compiler/runtime edit API behavior from `codex/kg-generation-pipeline-refactor`.
* Only port reasoning adaptor contracts that are still meaningful on top of the refactored backend.
* Drop generated temporary outputs unless a specific artifact is intentionally promoted.

## Open Questions

* None blocking yet; derive the first-pass include/drop decisions from repository diffs and tests.

## Requirements (Evolving)

* Create a file-level keep / port manually / drop inventory before editing contested backend modules.
* Keep the integration branch based on `codex/kg-generation-pipeline-refactor`.
* Avoid whole-file replacement for conflict-heavy backend files.
* Preserve project rules for source-constrained KG generation and feedback-compatible outputs.
* Do not commit large temporary experiment outputs.

## Acceptance Criteria (Evolving)

* [x] Low-risk reasoning adaptor files are selectively restored onto the integration branch.
* [x] Backend API and service changes are manually ported without reviving removed legacy KG construction modules.
* [x] Tests covering reasoning adaptor contracts pass, or failures are documented with concrete next steps.
* [x] The final diff excludes `tmp*` generated outputs and unrelated Trellis history churn.

## Definition of Done

* Tests added/updated where appropriate.
* Relevant unit/API tests run.
* Docs/notes updated if behavior changes.
* Rollback path is clear: integration branch can be abandoned without touching source branches.

## Out of Scope

* Rewriting the KG generation pipeline architecture.
* Merging old `src/kgtracevis/kg_construction/*` modules back into the refactored pipeline.
* Committing generated `tmp*` run artifacts.
* Pushing or opening a PR unless requested separately.

## Technical Notes

* Direct merge conflict dry-run was produced with `git merge-tree codex/kg-generation-pipeline-refactor codex/reasoning_adaptor`.
* Initial conflict cluster: `src/kgtracevis/service/api.py`, `src/kgtracevis/service/kg_construction.py`, `src/kgtracevis/service/kg_materials.py`, `src/kgtracevis/service/kg_drafts.py`, `src/kgtracevis/service/kg_material_build.py`, `src/kgtracevis/core/result.py`, `src/kgtracevis/core/rca.py`, `src/kgtracevis/kg/path_ranker.py`, and related tests.
* Verification passed: `uv run --extra dev pytest`, `uv run python scripts/run_examples.py`, `uv run --extra dev ruff check .`, `uv run --extra dev mypy src tests scripts`, `cd web && npm run typecheck`, and `cd web && npm run build`.

## File Disposition

### Keep / Restore Directly

* `configs/reasoning_profiles/*/manifest.json`
* `src/kgtracevis/core/reasoning_profile.py`
* `src/kgtracevis/workflows/reasoning_registry.py`
* `tests/test_reasoning_registry.py`
* `docs/frontend_handoff.md`
* `docs/reasoning_adapter_profile_refactor_plan_cn.md`
* `web/vite.config.ts`

### Port Manually

* `src/kgtracevis/workflows/root_cause_provider_selection.py`
* `src/kgtracevis/core/pipeline.py`
* `src/kgtracevis/core/rca.py`
* `src/kgtracevis/core/result.py`
* `src/kgtracevis/kg/path_ranker.py`
* `src/kgtracevis/service/api.py`
* `src/kgtracevis/service/runs.py`
* `web/src/api/contracts.ts`
* `web/src/api/client.ts`

### Drop From Reasoning Branch

* Generated `tmp*` outputs.
* Old `src/kgtracevis/kg_construction/*` modules and legacy scripts revived by the stale frontend branch.
* Deletions of runtime KG edit APIs, construction build jobs, review queue contracts, source KG compiler contracts, and overlay provenance behavior.
