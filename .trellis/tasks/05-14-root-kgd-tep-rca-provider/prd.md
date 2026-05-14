# Root-KGD TEP RCA Provider

## Goal

Implement a first-class TEP Root-KGD RCA provider inside KGTraceVis that computes root-cause rankings from the current Evidence at runtime using TEP_KG model assets and logic, then integrate it with `KGTracePipeline` as the native TEP RCA provider.

## What I Already Know

* The implementation must run in `/Users/hhm/code/KGTraceVis`.
* Public artifact-provider mode is not the desired solution.
* The main flow must not rank by reading precomputed per-scenario ranking files.
* The provider must compute from current Evidence at runtime and structurally adapt the TEP_KG Root-KGD logic 1:1.
* Existing unrelated MVTec/default PatchCore edits and the analysis document must not be reverted.
* Prior artifact-provider exposure may be removed if it conflicts with this task.

## Requirements

* Preserve/finalize TEP producer defaults aligned to TEP_KG:
  * `window_size=100`
  * `row_stride=25`
  * `n_components=18`
  * `fault_free_max_rows=None`
  * explicit overrides must still work.
* Remove/undo public CLI/evaluation additions that expose `--tep-rca-provider artifact/native/none` in `evaluate_tep_rca` and the adapter pipeline if added by prior interrupted work.
* Add a Root-KGD implementation under `src/kgtracevis/` that ports TEP_KG logic from `/Users/hhm/code/TEP_KG/src/tep_kg/root_kgd.py` and support modules, adapted to KGTraceVis schemas.
* Load propagation graph and model parameters from model asset files, not from KGTraceVis `tep_edges.csv` direct-support graph.
* Support relation params, trained edge weights, anchor discriminators, and anchor memory profiles.
* Preserve the TEP_KG algorithms for weighted contributions, candidate enumeration, propagation simulation, ranking score, anchor discriminator alignment, anchor memory alignment, adjustments, and tie-breaks.
* Implement `reason_root_causes(evidence, graph, linked_entities, top_k)` returning `RcaReasoningResult` with `ranked_root_causes` and `top_k_paths`/explanation paths in KGTraceVis schemas.
* Do not use `fault_number` as scoring input; fault/run may remain metadata/evaluation reference only.
* Copy only runtime model/graph assets into `data/kg/tep_root_kgd/`:
  * `nodes.jsonl`
  * `edges.jsonl`
  * `tep_variable_mapping.jsonl`
  * `anchor_discriminators.json`
  * `relation_family_params.json`
  * `rca_edge_weights.jsonl`
  * `anchor_memory_profiles.json`
* Do not copy/use per-scenario ranking files such as `baseline_root_scores.csv`, `topk_subgraphs.json`, or `rbc_contributions.jsonl` as runtime ranking inputs.
* Treat `anchor_memory_profiles.json` as learned model parameters, not as sample ranking output.
* Ensure current TEP Evidence carries enough current-sample signals:
  * full `channel_contributions` in `raw_evidence.extra` must be usable;
  * add `graph_contributions` mapped to Root-KGD variable ids if useful;
  * add current-window dynamic features compatible with TEP_KG `scenario_dynamic_features` if feasible;
  * dynamic features must not leak `fault_number` into scoring.
* Make native TEP RCA provider mean the real Root-KGD provider.
* Keep old direct-support provider only as explicit simple/fallback if necessary.
* Keep candidate/plausible claim boundaries and do not add unsupported industrial claims.

## Acceptance Criteria

* [x] Native TEP provider selection builds the Root-KGD provider.
* [x] Runtime ranking changes when Evidence contributions change, without reading precomputed ranking rows.
* [x] TEP producer defaults match TEP_KG while explicit overrides remain honored.
* [x] TEP Evidence exposes Root-KGD-compatible contribution and dynamic-feature signals.
* [x] Focused synthetic asset tests cover provider scoring from current Evidence.
* [x] Optional real TEP_KG parity/smoke test is skipped when `/Users/hhm/code/TEP_KG` is absent.
* [x] Focused producer tests cover defaults and dynamic feature presence.
* [x] Focused provider selection tests cover native Root-KGD behavior.
* [x] Ruff and focused pytest pass for changed files.

## Definition of Done

* Tests added/updated for the provider, producer defaults/features, and provider selection.
* Focused lint/check commands run and reported.
* Public docs or CLI help updated only where behavior changes are user-facing.
* No unrelated worktree edits are reverted.

## Out of Scope

* Building public artifact mode as the recommended or expanded path.
* Reading precomputed per-scenario ranking outputs as runtime ranking inputs.
* Reworking MVTec/default PatchCore behavior beyond avoiding conflicts.
* Claiming verified TEP industrial causal facts beyond the source-constrained assets.

## Technical Notes

* Source Root-KGD implementation: `/Users/hhm/code/TEP_KG/src/tep_kg/root_kgd.py` plus support modules.
* Target Root-KGD asset directory: `data/kg/tep_root_kgd/`.
* Task created from the user request on 2026-05-14.
