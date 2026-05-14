# TEP RCA Integration Current-State Research

## Scope

Read-only survey of:

* `/Users/hhm/code/KGTraceVis`
* `/Users/hhm/code/TEP_KG`
* `/Users/hhm/code/RootLens`

The user asked to research the current state before implementing TEP RCA inference integration. Another Agent is working on KG construction and unification, so this note focuses on the RCA reasoning consumer side.

## KGTraceVis Current State

Relevant existing pieces:

* `src/kgtracevis/adapters/tep_adapter.py` converts TEP-style records into unified `Evidence`, including variable observations and contribution values.
* `src/kgtracevis/core/pipeline.py` runs the current generic KGTrace pipeline: entity linking, consistency, correction candidates, and path ranking.
* `src/kgtracevis/kg/path_ranker.py` is route1-style relation-weighted path ranking over `KnowledgeGraph`.
* `src/kgtracevis/service/runs.py`, `run_steps.py`, and `run_enrichment.py` already persist analysis results, path graphs, provenance, and review targets for the web analysis surface.
* `data/examples/tep_example.json` exists, but `data/kg/tep_nodes.csv` and `data/kg/tep_edges.csv` currently contain only headers, so out-of-the-box TEP route1 reasoning has no meaningful graph unless Neo4j or explicit overlays provide TEP nodes/edges.
* `docs/tep_kg_merge_assessment.md` and `docs/source_to_kg_construction_system.md` already define the preferred KG construction merge path.
* `src/kgtracevis/kg_construction/tep_import.py` already contains `TepSemanticLiftExtractor` and `TepVariableMappingExtractor`.
* `scripts/build_source_kg.py` can build candidate KG CSV overlays from TEP_KG semantic lift and variable mapping sources.

Current gap:

* There is no dedicated TEP RCA route2/result model in `AnalysisResult`.
* There is no workflow/provider that consumes TEP_KG `rbc_contributions`, Root-KGD rankings, or Root-KGD generated subgraphs.
* The generic path ranker has no relation-family or propagation semantics.
* TEP default CSV seed files are empty, and default in-memory paths do not include `tep_nodes.csv` / `tep_edges.csv`.

## TEP_KG Current State

Relevant RCA assets:

* `src/tep_kg/rbc.py` generates robust baseline contribution scenarios from TEP CSV windows and maps TEP channels to KG entities.
* `data/processed/rca/rbc_contributions.jsonl` stores per-scenario contribution vectors, top variables, channel contributions, fault numbers, simulation runs, and mapping metadata.
* `src/tep_kg/propagation.py` builds propagation graphs using relation families, propagation flags, relation priors, edge weights, and bounded propagation.
* `src/tep_kg/root_kgd.py` ranks scenarios by:
  * enumerating candidates around high-contribution variables and root-cause anchors,
  * simulating propagation from each candidate,
  * comparing propagated variable patterns against observed contribution vectors by cosine similarity,
  * applying structural penalties/biases,
  * adding anchor discriminator, dynamic feature, and anchor memory adjustments,
  * emitting ranked candidates and top-k subgraphs.
* `outputs/rca/baseline_root_scores.csv` and `outputs/rca/baseline_topk_subgraphs.json` contain current Root-KGD style output.
* `outputs/rca/topk_subgraphs.json`, `outputs/rca/hit_rate_report.json`, and `outputs/rca/current_hit_rate.json` provide evaluated artifacts.

Important local mismatch:

* RootLens expects `data/processed/models/root_kgd_rankings.jsonl`, but the local `/Users/hhm/code/TEP_KG` currently has `data/processed/models/root_cause_rankings.jsonl` and `outputs/rca/baseline_root_scores.csv`.
* Therefore KGTraceVis should not hardcode RootLens paths. It should support configurable artifact paths and/or parse the current output forms.

Useful reusable contracts:

* TEP scenario identity: `scenario_id`, `fault_number`, `simulation_run`.
* RCA input: `graph_contributions`, `top_variables`, `top_channels`, `mapping_meta`.
* Candidate output: `candidate_id`, `candidate_name`, `candidate_type`, `candidate_role`, `rank`, `root_score`, `ranking_score`, `structural_ranking_score`, `ranking_adjustment`, `top_affected_variables`, `top_support_paths`, `support_evidence_ids`.
* Graph semantics: `relation_family`, `propagation_enabled`, `edge_weight`.

## RootLens Current State

RootLens is valuable as an integration reference rather than code to copy.

Relevant pieces:

* `src/doc/module-3-rca-engine.md` explicitly defines two independent RCA routes:
  * route1: KGTraceVis entity linking, consistency, correction, path ranking.
  * route2: TEP_KG Root-KGD scenario and ranking artifacts.
* `scripts/build-runtime.py` builds static `rootlens-runtime.json` by importing KGTraceVis and TEP_KG logic/artifacts.
* Route2 in `build-runtime.py` does not recompute Root-KGD; it indexes `rbc_contributions.jsonl` and `root_kgd_rankings.jsonl`, maps ranking rows into runtime candidate objects, builds route1/route2 cross-route signals, and validates exact ranking parity.
* `src/types/rootlens.ts` is a good front-end contract reference for route2 output shape.
* `src/services/local-reasoning.ts` contains browser fallback heuristics but is explicitly lower-fidelity than upstream Python parity runtime.

Risks if copied directly:

* `scripts/build-runtime.py` has hardcoded absolute paths from another machine (`/Users/bytedance/...`).
* The RootLens runtime format is static-file oriented, whereas KGTraceVis now has service/run-store APIs and Neo4j/Postgres runtime foundations.
* Browser fallback route2 is heuristic and should not become KGTraceVis backend truth.

## Integration Recommendation

Use a staged provider approach:

1. Keep KG construction work owned by the other Agent:
   * TEP semantic/runtime KG publication.
   * TEP variable mapping extraction.
   * TEP RCA anchor/edge publication if needed.

2. Add a KGTraceVis-side TEP RCA reasoning provider:
   * Reads TEP RCA artifacts from configured paths.
   * Matches by `case_id == scenario_id` when evidence comes from TEP_KG/RBC scenarios.
   * Falls back to constructing a lightweight route2 input from `raw_evidence.variable_contributions` when no precomputed scenario exists.
   * Emits stable Pydantic result objects compatible with web analysis and feedback.

3. Extend analysis output without breaking generic pipeline:
   * Keep existing `top_k_paths` as route1.
   * Add optional `tep_rca` or `root_kgd` field under `AnalysisResult` or a new richer envelope.
   * For web/run detail, expose route2 candidates as review targets and source-edge/source-evidence provenance.

4. Add a small offline script/API path first:
   * `src/kgtracevis/workflows/tep_rca.py`
   * optional `scripts/run_tep_rca.py`
   * tests using a tiny fixture extracted from TEP_KG artifacts, not the full generated outputs.

5. Later merge with web UX:
   * Show route1 path ranking and route2 Root-KGD candidates side by side.
   * Compute cross-route signals where route1 path targets overlap route2 candidates.
   * Keep RootLens-style static runtime import as a reference only.

## Implementation Candidate Files

Likely new or modified files if implementation proceeds:

* `src/kgtracevis/core/result.py`
* `src/kgtracevis/core/pipeline.py`
* `src/kgtracevis/workflows/tep_rca.py`
* `src/kgtracevis/service/run_models.py`
* `src/kgtracevis/service/runs.py`
* `src/kgtracevis/service/run_enrichment.py`
* `scripts/run_tep_rca.py`
* `tests/test_tep_rca_workflow.py`
* possibly `web/src/features/analysis/AnalysisPages.tsx` for UI after backend is ready

## MVP Boundary

Recommended MVP:

* Do not recompute TEP_KG Root-KGD training in KGTraceVis.
* Do not copy `TEP_KG/src/tep_kg/root_kgd.py` wholesale.
* Do not invent new KG causal facts.
* Consume existing TEP_KG Root-KGD artifacts as source-constrained, provenance-carrying RCA candidate outputs.
* Keep route2 claims as candidate/plausible explanations, not verified ground truth.

