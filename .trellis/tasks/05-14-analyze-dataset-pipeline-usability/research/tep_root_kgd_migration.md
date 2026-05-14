# Research: TEP Root-KGD migration

- Query: Compare TEP_KG Root-KGD implementation with KGTraceVis integration requirements for 1:1 inference parity.
- Scope: mixed
- Date: 2026-05-14

## Findings

### Files Found

- `../TEP_KG/src/tep_kg/rbc.py` - RBC profile fitting, faulty-window collection, channel-to-KG-variable mapping, and offline scenario artifact generation.
- `../TEP_KG/src/tep_kg/propagation.py` - Root-KGD RFPA-style propagation graph construction, relation weights, candidate source selection, simulation, and path tracing.
- `../TEP_KG/src/tep_kg/rca_signal_utils.py` - shared contribution weighting and cosine/signature helpers used by Root-KGD and anchor memory.
- `../TEP_KG/src/tep_kg/anchor_discriminators.py` - curated/LLM-assisted diagnostic variable sets for fault anchors.
- `../TEP_KG/src/tep_kg/anchor_memory.py` - historical anchor contribution/dynamic centroids and runtime alignment bonus.
- `../TEP_KG/src/tep_kg/scenario_dynamic_features.py` - window-level z-score mean/slope/osc/std feature extraction.
- `../TEP_KG/src/tep_kg/root_kgd.py` - Root-KGD ranking, special ranking adjustments, top-k subgraph export, and batch artifact writer.
- `src/kgtracevis/workflows/tep_rca.py` - current KGTraceVis TEP artifact bridge and native provider; not a 1:1 Root-KGD port.
- `src/kgtracevis/producers/tep_records.py` and `src/kgtracevis/adapters/tep_adapter.py` - current Evidence producer/adapter path for TEP residual contributions.
- `src/kgtracevis/core/rca.py` and `src/kgtracevis/core/pipeline.py` - unified reasoner contract and pipeline integration point.
- `docs/dataset_pipeline_usability_analysis.md` - prior comparison notes, including the samples 1-20 parity trap and updated TEP_KG-like defaults.
- `.trellis/spec/backend/adapter-guidelines.md`, `.trellis/spec/backend/workflow-architecture.md`, `.trellis/spec/backend/database-guidelines.md` - relevant integration contracts.

### Modules / Functions To Port For 1:1 Root-KGD Inference

The minimum faithful port is not just a new score function. It is this chain:

1. RBC and mapping surface:
   - `rbc.stable_id`, `clamp`, `load_tep_mapping`, `fit_fault_free_profile`, `collect_fault_windows`, `compute_rbc_contributions`, `map_channel_contributions`, and `build_rbc_scenarios` define the exact contribution vectors and `variable:*` graph IDs consumed by Root-KGD (`../TEP_KG/src/tep_kg/rbc.py:15`, `../TEP_KG/src/tep_kg/rbc.py:52`, `../TEP_KG/src/tep_kg/rbc.py:209`, `../TEP_KG/src/tep_kg/rbc.py:278`, `../TEP_KG/src/tep_kg/rbc.py:346`, `../TEP_KG/src/tep_kg/rbc.py:397`, `../TEP_KG/src/tep_kg/rbc.py:437`).
   - TEP_KG computes PCA rank by variance threshold with min/max clamps, defaulting to threshold `0.95`, min rank `6`, max rank `18`; KGTraceVis currently uses fixed `n_components=18` in its numpy producer (`../TEP_KG/src/tep_kg/rbc.py:21`, `../TEP_KG/src/tep_kg/rbc.py:244`, `src/kgtracevis/producers/tep_records.py:22`, `src/kgtracevis/producers/tep_records.py:24`, `src/kgtracevis/producers/tep_records.py:165`).

2. Propagation:
   - Port `RELATION_LOGIT_PRIORS`, `DEFAULT_RELATION_PARAMS`, `initial_edge_weight`, `build_propagation_graph`, `candidate_source_ids`, `incident_neighbors`, `simulate_propagation`, and `trace_path` (`../TEP_KG/src/tep_kg/propagation.py:13`, `../TEP_KG/src/tep_kg/propagation.py:23`, `../TEP_KG/src/tep_kg/propagation.py:66`, `../TEP_KG/src/tep_kg/propagation.py:88`, `../TEP_KG/src/tep_kg/propagation.py:138`, `../TEP_KG/src/tep_kg/propagation.py:154`, `../TEP_KG/src/tep_kg/propagation.py:163`, `../TEP_KG/src/tep_kg/propagation.py:232`).
   - This requires a Root-KGD reasoning graph shape with node fields such as `entity_type`, `candidate_role`, `root_cause_candidate`, `variable_role`, `fault_numbers`, and edge fields such as `relation_family`, `propagation_enabled`, `source_types`, `support_count`, `edge_origin`, and `provenance_ids`.

3. Shared signal helpers:
   - Port `VARIABLE_ROLE_CONTRIBUTION_WEIGHT`, `contribution_weight`, `weighted_contributions`, `dense_cosine_similarity`, `sparse_cosine_similarity`, and `sparse_signature_coverage` (`../TEP_KG/src/tep_kg/rca_signal_utils.py:8`, `../TEP_KG/src/tep_kg/rca_signal_utils.py:15`, `../TEP_KG/src/tep_kg/rca_signal_utils.py:23`, `../TEP_KG/src/tep_kg/rca_signal_utils.py:33`, `../TEP_KG/src/tep_kg/rca_signal_utils.py:42`, `../TEP_KG/src/tep_kg/rca_signal_utils.py:57`).

4. Anchor discriminators:
   - Port `SEED_DIAGNOSTIC_VARIABLES`, `SEED_SIBLING_OVERRIDES`, `load_anchor_discriminators`, `_normalize_anchor_output`, `_seed_anchor_output`, `_stabilize_anchor_output`, and `build_anchor_discriminators` if KGTraceVis will own rebuilding; for inference only, load a frozen discriminator artifact through a schema-validated asset (`../TEP_KG/src/tep_kg/anchor_discriminators.py:16`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:72`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:180`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:312`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:338`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:360`, `../TEP_KG/src/tep_kg/anchor_discriminators.py:373`).

5. Anchor memory:
   - Port constants and `build_anchor_memory_profiles`, `anchor_memory_alignment_details`, `anchor_memory_alignment`, and `anchor_memory_payload` (`../TEP_KG/src/tep_kg/anchor_memory.py:14`, `../TEP_KG/src/tep_kg/anchor_memory.py:207`, `../TEP_KG/src/tep_kg/anchor_memory.py:297`, `../TEP_KG/src/tep_kg/anchor_memory.py:371`, `../TEP_KG/src/tep_kg/anchor_memory.py:393`).
   - Runtime inference should use a frozen anchor-memory profile trained on training/reference scenarios, not rebuild memory from the case being ranked.

6. Scenario dynamic features:
   - Port `_fault_free_baseline`, `_summarize_window`, `build_dynamic_features_for_scenarios`, and `load_scenario_dynamic_features` logic, but adapt runtime to compute the current Evidence window feature vector instead of requiring a scenario-id lookup (`../TEP_KG/src/tep_kg/scenario_dynamic_features.py:68`, `../TEP_KG/src/tep_kg/scenario_dynamic_features.py:117`, `../TEP_KG/src/tep_kg/scenario_dynamic_features.py:142`, `../TEP_KG/src/tep_kg/scenario_dynamic_features.py:261`).

7. Root-KGD ranking:
   - Port `variable_order`, `_downstream_contribution_signal`, `enumerate_candidates`, `_candidate_seed_score`, `_pattern_entropy`, `ranking_score`, `_anchor_discriminator_alignment`, `_ranking_sort_key`, all `_apply_*_adjustments`, `_support_payload`, `rank_scenario`, and optionally `build_topk_subgraphs` for explanation export (`../TEP_KG/src/tep_kg/root_kgd.py:253`, `../TEP_KG/src/tep_kg/root_kgd.py:257`, `../TEP_KG/src/tep_kg/root_kgd.py:295`, `../TEP_KG/src/tep_kg/root_kgd.py:438`, `../TEP_KG/src/tep_kg/root_kgd.py:471`, `../TEP_KG/src/tep_kg/root_kgd.py:483`, `../TEP_KG/src/tep_kg/root_kgd.py:513`, `../TEP_KG/src/tep_kg/root_kgd.py:544`, `../TEP_KG/src/tep_kg/root_kgd.py:662`, `../TEP_KG/src/tep_kg/root_kgd.py:692`, `../TEP_KG/src/tep_kg/root_kgd.py:784`, `../TEP_KG/src/tep_kg/root_kgd.py:869`, `../TEP_KG/src/tep_kg/root_kgd.py:914`, `../TEP_KG/src/tep_kg/root_kgd.py:1001`, `../TEP_KG/src/tep_kg/root_kgd.py:1085`, `../TEP_KG/src/tep_kg/root_kgd.py:1144`, `../TEP_KG/src/tep_kg/root_kgd.py:1230`, `../TEP_KG/src/tep_kg/root_kgd.py:1316`, `../TEP_KG/src/tep_kg/root_kgd.py:1414`, `../TEP_KG/src/tep_kg/root_kgd.py:1532`, `../TEP_KG/src/tep_kg/root_kgd.py:1587`, `../TEP_KG/src/tep_kg/root_kgd.py:1616`, `../TEP_KG/src/tep_kg/root_kgd.py:1822`).
   - `build_root_kgd` is a batch artifact writer, not the desired KGTraceVis runtime API. Its sequence shows dependencies and output files, but a KGTraceVis provider should expose `reason_root_causes(...)` under the existing reasoner contract (`../TEP_KG/src/tep_kg/root_kgd.py:2026`, `src/kgtracevis/core/rca.py:16`, `src/kgtracevis/core/pipeline.py:101`).

### Asset vs Output Artifact Classification

Runtime/model assets needed or useful for KGTraceVis Root-KGD:

- Root-KGD reasoning graph asset: TEP_KG `data/processed/rca/nodes.jsonl` and `edges.jsonl`, or a KGTraceVis-compatible equivalent preserving propagation fields.
- TEP 52-channel mapping asset: `data/processed/kg/tep_variable_mapping.jsonl`; needed to map `xmeas_*`/`xmv_*` to `variable:*` graph IDs.
- Optional alignment asset: `data/processed/kg/entity_alignment_edges.jsonl`; affects RBC mapping metadata and edge initialization.
- Producer model asset: `data/processed/rca/rbc_profile.json`; only needed when KGTraceVis itself computes RBC from raw windows. Once Evidence already carries contributions, it is not a ranking input.
- Discriminator asset: `data/processed/rca/anchor_discriminators.json`; runtime ranking input.
- Anchor memory asset: `outputs/rca/anchor_memory_profiles.json` or a KGTraceVis-managed frozen equivalent; runtime ranking input if the Root-KGD port keeps anchor-memory bonuses.
- Relation parameter asset: defaults from `propagation.DEFAULT_RELATION_PARAMS`, or a validated config.

Per-scenario output artifacts / evaluation artifacts:

- `data/processed/rca/rbc_contributions.jsonl`: offline scenario evidence produced from TEP_KG raw CSV windows. It is a valid parity fixture and artifact-bridge selector source, but it should not be a runtime ranking input for KGTraceVis Evidence-driven inference. Runtime should build the `scenario` dict from the current Evidence's `graph_contributions`, dynamic features, fault/run metadata, and case ID.
- `outputs/rca/baseline_root_scores.csv`: Root-KGD ranking output. Explicitly not a runtime ranking input.
- `outputs/rca/baseline_topk_subgraphs.json` / `outputs/rca/topk_subgraphs.json`: explanation/export output. Explicitly not a runtime ranking input.
- `outputs/rca/*hit_rate*`, `training_*`, `explanation_examples.*`, holdout/expanded-run ranking CSV/JSONL files: evaluation and reporting outputs, not runtime inputs.

KGTraceVis currently has an artifact bridge that can read `baseline_root_scores.csv` and `rbc_contributions.jsonl` (`src/kgtracevis/workflows/tep_rca.py:770`, `src/kgtracevis/workflows/tep_rca.py:786`). That bridge is useful for compatibility checks, but 1:1 Root-KGD inference should not depend on precomputed ranking rows.

### How Evidence Should Feed Root-KGD Inputs

KGTraceVis Evidence has the right envelope: `raw_evidence.variables`, `raw_evidence.variable_contributions`, `raw_evidence.extra`, `observations`, and `normalized_evidence` (`src/kgtracevis/schema/evidence_schema.py:13`, `src/kgtracevis/schema/evidence_schema.py:25`, `src/kgtracevis/schema/evidence_schema.py:63`). The provider should convert one Evidence case into the TEP_KG `scenario` shape expected by `rank_scenario`:

- `scenario_id`: `raw_evidence.extra["scenario_id"]` when supplied, else `case_id`.
- `fault_number` / `simulation_run`: pass through for evaluation metadata and anchor-memory training lookup only; do not use fault number to pick the answer for runtime scoring.
- `sample_start`, `sample_end`, `window_size`: from TEP producer metadata; current producer emits these fields (`src/kgtracevis/producers/tep_records.py:327`).
- `graph_contributions`: prefer existing `raw_evidence.extra["graph_contributions"]` if present and already uses `variable:*` IDs; else map `raw_evidence.extra["channel_contributions"]` or `raw_evidence.variable_contributions` through the TEP 52-channel mapping. Current producer only stores top variables in `variable_contributions`, but it stores full `channel_contributions` under `extra` (`src/kgtracevis/producers/tep_records.py:321`, `src/kgtracevis/producers/tep_records.py:349`).
- Dynamic feature vector: prefer `normalized_evidence["dynamic_features"]` or `raw_evidence.extra["dynamic_features"]`; if absent, compute from the raw window rows and a fault-free baseline using the TEP_KG dynamic-feature formula. Current Evidence does not carry raw window rows, so a 1:1 runtime provider needs either window row access by `raw_data_path` + sample range or producer-emitted dynamic features.
- The provider must return `RcaReasoningResult` with aligned `top_k_paths` and `ranked_root_causes` so service/Postgres/frontend code preserves provider rankings (`src/kgtracevis/core/rca.py:16`, `src/kgtracevis/core/pipeline.py:65`, `.trellis/spec/backend/database-guidelines.md:107`).

Current KGTraceVis extraction already gathers contributions from raw, extra, normalized fields, and observations (`src/kgtracevis/workflows/tep_rca.py:186`), but the native provider ranks by shortest support paths and a simpler formula (`src/kgtracevis/workflows/tep_rca.py:423`, `src/kgtracevis/workflows/tep_rca.py:495`). It does not implement Root-KGD propagation, cosine RootScore, anchor discriminators, anchor memory, dynamic signatures, or the special ranking adjustments.

### Known Parity Traps

- Samples 1-20 issue: prior analysis found fault 1/2/6 simulationRun 1 samples 1-20 are identical through sample 20 and first differ at sample 21; both KGTraceVis and TEP_KG produce the same unhelpful top variables under `window_size=20`, so this is a bad parity/evaluation window (`docs/dataset_pipeline_usability_analysis.md:542`, `docs/dataset_pipeline_usability_analysis.md:557`, `docs/dataset_pipeline_usability_analysis.md:568`). Use `window_size=100`, `row_stride=25`, `fault_free_max_rows=None`, `pca_rank/n_components=18` for TEP_KG-style comparisons (`docs/dataset_pipeline_usability_analysis.md:581`, `docs/dataset_pipeline_usability_analysis.md:620`).
- PCA rank/defaults: TEP_KG chooses rank from explained variance and clamps to 6..18; KGTraceVis currently defaults to fixed `n_components=18`. For exact offline RBC parity, either port TEP_KG's rank-selection behavior or explicitly assert fixed-18 parity against a TEP_KG run configured the same way.
- Anchor memory semantics: `build_anchor_memory_profiles` groups historical scenarios by graph `fault_numbers` on FaultAnchor nodes and averages contribution/dynamic centroids (`../TEP_KG/src/tep_kg/anchor_memory.py:207`). Runtime must not rebuild the memory profile from the current case; doing so leaks label/context and inflates alignment.
- Artifact bridge trap: `baseline_root_scores.csv` gives answers, not a model. Using it during runtime makes KGTraceVis replay TEP_KG outputs rather than perform inference.
- Graph schema trap: TEP_KG uses colon IDs and rich RCA JSONL fields; KGTraceVis seed CSVs use PascalCase-like IDs and a simpler edge contract. A 1:1 port must either preserve a private Root-KGD graph view or add a translation layer without losing `relation_family`, `propagation_enabled`, candidate roles, variable roles, source types, support counts, and provenance.

### Suggested Acceptance Tests

- RBC parity fixture: for a small controlled TEP CSV fixture, assert KGTraceVis port reproduces TEP_KG `fit_fault_free_profile`, `compute_rbc_contributions`, and `map_channel_contributions` within tolerance for the same rank/defaults.
- Evidence-to-scenario test: Evidence with full `extra.channel_contributions` maps to `graph_contributions` for all 52 variables, not only top variables; Evidence with pre-mapped `extra.graph_contributions` is used directly.
- No artifact-ranking input test: configure Root-KGD provider with graph/mapping/discriminator/memory assets but no `baseline_root_scores.csv` or `topk_subgraphs`; ranking still works. Add a negative guard that `baseline_root_scores.csv` is only accepted by `TepRcaArtifactProvider`, not the native Root-KGD provider.
- Samples 1-20 trap regression: assert faults 1/2/6 run 1 windows 1-20 produce indistinguishable or matching top variables, and mark this as non-acceptance for RCA quality; assert `window_size=100` reproduces the TEP_KG-style top variables documented for faults 1/2/6.
- Root-KGD rank parity: for fixed TEP_KG artifacts/graph and generated Evidence for fault 1/2/6 run 1 samples 1-100, assert top-1 or full top-k order matches TEP_KG `rank_scenario` rows.
- Ranking adjustment unit tests: port TEP_KG tests for `_anchor_discriminator_alignment`, `_apply_anchor_preference_adjustments`, separator family, condenser/stream4/stream2/stripper dynamic/tiebreak adjustments (`../TEP_KG/tests/test_root_kgd_anchor_preference.py:13`).
- Anchor memory tests: port tests asserting matching anchors receive larger contribution/dynamic bonuses and non-root-cause candidates get zero memory bonus (`../TEP_KG/tests/test_anchor_memory.py:103`, `../TEP_KG/tests/test_anchor_memory.py:112`).
- Unified contract test: provider returns `RcaReasoningResult` with nonempty `ranked_root_causes`, aligned `top_k_paths`, stable IDs, source edges/evidence, `scoring_method="tep_root_kgd"`, and `uses_fault_number_for_scoring=false`.
- Scope test: mixed graph containing `mvtec` or unrelated `shared` nodes must not let non-TEP candidates enter Root-KGD candidate enumeration unless the private Root-KGD graph view explicitly allows them.

### External References

- `../TEP_KG/docs/Root-KGD.md` summarizes Root-KGD as RBC contribution extraction plus RFPA propagation plus cosine RootScore alignment; it also notes the paper's use of the first 100 post-fault samples (`../TEP_KG/docs/Root-KGD.md:23`, `../TEP_KG/docs/Root-KGD.md:41`, `../TEP_KG/docs/Root-KGD.md:63`).
- No web references were needed; this research used local repositories and local Trellis specs.

### Related Specs

- Adapter rules: producers/adapters may emit observed variables/contributions but must not emit root causes or ranking outputs; KG analysis must be computed later.
- Workflow architecture: TEP Root-KGD belongs behind `RcaReasoner.reason_root_causes(...)`, not in scripts, adapters, or service routes.
- Database/runtime payload rules: preserve provider `ranked_root_causes` and only derive fallback from `top_k_paths` when no provider candidates exist.

## Caveats / Not Found

- I did not modify source code or run parity tests; this is research-only.
- I did not verify a full TEP_KG run during this pass; existing local code, tests, artifacts, and prior analysis were read.
- Exact 1:1 parity requires either preserving TEP_KG's private Root-KGD graph representation or proving a lossless KGTraceVis graph translation. Current KGTraceVis native provider is integration-compatible but algorithmically different.
