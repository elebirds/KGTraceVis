# Unified TEP RCA Pipeline Design

## Goal

Unify the TEP_KG RCA flow into KGTraceVis without keeping `/Users/hhm/code/TEP_KG` as a long-term runtime dependency.

The target is not to run two parallel RCA systems. The target is one KGTraceVis RCA pipeline contract with scenario-specific strategy hooks where the evidence modality requires different scoring logic.

```text
TEP raw records / windows
-> KGTraceVis Evidence
-> KGTraceVis KG snapshot
-> unified RCA engine
   -> shared evidence/KG grounding
   -> scenario-specific candidate scoring strategy
-> unified analysis envelope
-> service / web / metrics / feedback
```

## Design Principle

Keep a single orchestration spine and allow dataset-specific reasoning strategies.

Shared spine:

* source/config resolution
* evidence validation
* KG snapshot selection
* entity linking
* consistency checking
* candidate correction
* result envelope
* run persistence
* provenance and feedback targets
* metrics/reporting hooks

TEP-specific strategy:

* TEP channel mapping
* RBC feature extraction
* contribution vector building
* propagation graph view
* Root-KGD candidate ranking
* TEP fault-label evaluation

This gives one product pipeline while avoiding a fake one-size-fits-all scoring formula.

Avoid the mental model:

```text
route1: generic paths
route2: TEP RCA
```

Use this model instead:

```text
Unified RCA Engine
  Evidence grounding
  KG candidate retrieval
  Candidate scoring strategy
    image/wafer: relation-weighted path scoring
    tep: process-propagation scoring
  Explanation materialization
  Feedback-compatible result
```

## Target Architecture

```text
src/kgtracevis/
  adapters/
    tep_adapter.py
      raw TEP record/window -> Evidence

  kg_construction/
    tep_import.py
      TEP semantic/RCA graph source -> DraftKG -> KG CSV/Neo4j

  workflows/
    tep_rca/
      records.py
        raw CSV/window loading and scenario records
      channel_mapping.py
        xmeas/xmv -> KG entity mapping
      rbc.py
        fault-free profile + contribution extraction
      propagation.py
        relation-family graph view and propagation
      root_kgd.py
        candidate enumeration + ranking
      evaluation.py
        TEP hit-rate/MRR/path-hit reports
      models.py
        Pydantic contracts for route2 result
      workflow.py
        public entry point

  core/
    pipeline.py
      common KGTracePipeline plus unified RCA engine

  service/
    runs.py / run_enrichment.py / run_models.py
      persist and expose one unified RCA result shape
```

## Pipeline Shape

### Stage 0: Runtime Configuration

Inputs:

* `configs/paths.yaml`
* optional env vars
* user upload/run request

Resolved resources:

* TEP raw dataset paths
* fault-free profile cache path
* KG snapshot id/version
* optional precomputed artifacts for transition mode
* output directory under `runs/` or `outputs/`

Rule:

* No hard-coded absolute paths.
* External TEP_KG paths are allowed only in bridge mode and must be explicit config.

### Stage 1: Evidence Ingestion

Use the existing unified evidence schema.

TEP inputs can be:

* one JSON Evidence file
* structured TEP record JSON/JSONL/CSV
* future TEP raw time-series window

Output:

```text
Evidence(dataset="tep", source="time_series")
```

TEP observations should include:

* variable observations for top abnormal channels
* contribution scores
* time window metadata
* fault/run/sample metadata in `raw_evidence.extra`
* no root-cause label as observed evidence

### Stage 2: KG Snapshot Selection

Current generic behavior:

```text
KGTracePipeline.graph_for_evidence(evidence)
```

Target behavior:

```text
scenario=tep
-> shared KG + TEP semantic KG + TEP RCA view
```

The KG construction Agent owns how TEP semantic/RCA nodes and edges are published.

The RCA workflow needs the graph to preserve or expose:

* node labels/types
* aliases
* edge confidence/weight
* source/evidence/review status
* relation family
* propagation enabled flag
* root-cause candidate role

If CSV edge schema cannot yet hold metadata columns, use Neo4j properties or a sidecar artifact during transition. Long term, promote relation-family metadata into the runtime graph model.

### Stage 3: Unified Evidence/KG Grounding

This remains the first half of the existing KGTraceVis analysis:

```text
Evidence
-> entity_linker
-> consistency_checker
-> correction_generator
```

Output stays:

* linked entities
* consistency score
* inconsistent fields
* correction candidates
* candidate correction context

This stage is shared across all scenarios. It gives the RCA engine grounded entities and known inconsistencies before root-cause candidate scoring starts.

### Stage 4: Unified RCA Candidate Retrieval

The pipeline then retrieves root-cause candidates from the same KG snapshot.

The candidate representation should be shared:

```text
RcaCandidate
  candidate_id
  candidate_name
  candidate_label
  candidate_role
  anchor_entities
  supporting_paths
  supporting_edges
```

For MVTec/wafer this can be mostly path-derived. For TEP it can include root-cause anchors, equipment, streams, components, and actuator variables.

### Stage 5: Scenario Scoring Strategy

The scoring strategy is selected by dataset and available evidence features:

```text
dataset=mvtec/wafer -> PathScoringStrategy
dataset=tep         -> ProcessPropagationScoringStrategy
```

The strategy is not a second pipeline. It is the scoring implementation inside the unified RCA engine.

TEP strategy is only enabled when:

```text
evidence.dataset == "tep"
```

TEP scoring flow:

```text
Evidence or TEP window
-> TEP contribution vector
-> propagation graph view
-> candidate enumeration
-> simulate propagation per candidate
-> compare simulated variable pattern with observed vector
-> rank root-cause candidates
-> build support subgraphs
```

Substeps:

1. Normalize variable IDs:
   * `XMEAS_1`, `xmeas_1`, `variable:xmeas_1`, and KGTraceVis PascalCase IDs must map deterministically.

2. Build contribution vector:
   * For bridge mode: read from precomputed `rbc_contributions.jsonl` by `scenario_id`.
   * For native mode: compute from uploaded/raw TEP window using migrated RBC logic.

3. Build propagation graph view:
   * Use KGTraceVis `KnowledgeGraph` or Neo4j snapshot.
   * Filter to edges with `propagation_enabled=true` where available.
   * Use relation-family parameters for attenuation/priority.

4. Enumerate candidates:
   * root-cause anchors
   * equipment/stream/component candidates near top variables
   * optional actuator/variable candidates

5. Rank:
   * seed candidate
   * simulate propagation
   * score similarity against observed contribution vector
   * apply penalties/biases
   * apply TEP-specific optional adjustments only if their source/features are present

6. Explain:
   * top affected variables
   * support paths
   * supporting KG edges and evidence IDs
   * stable candidate IDs

Strategy output contract:

```text
RcaRankingResult
  ranked_candidates
  explanation_paths/support_subgraphs
  scoring_details
  metrics/debug optional
```

TEP-specific fields such as `fault_signature`, `top_affected_variables`, and propagation scores should live inside `scoring_details`, not in a separate top-level route.

### Stage 6: Explanation Materialization

The final RCA output should still look like one system:

```text
ranked_root_causes[]
  rank
  candidate_id
  candidate_name
  score
  confidence
  evidence_match
  explanation_paths[]
  supporting_edges[]
  supporting_evidence[]
  scoring_method
  scoring_details
```

For non-TEP scenarios, `explanation_paths` are the familiar top-k paths.

For TEP, `explanation_paths` are support paths/subgraphs produced by propagation and mapped back to KG edges where possible.

### Stage 7: Unified Analysis Envelope

Existing `AnalysisResult` should evolve toward:

```text
AnalysisResult
  case_id
  linked_entities
  consistency_score
  inconsistent_fields
  correction_candidates
  top_k_paths              # compatibility alias / path-oriented view
  ranked_root_causes       # unified RCA result
  human_feedback
```

Compatibility rule:

* Existing consumers can still read `top_k_paths`.
* New consumers should prefer `ranked_root_causes`.
* TEP does not appear as a separate route; it appears as root-cause candidates scored by `ProcessPropagationScoringStrategy`.

### Stage 8: Service And Web Integration

Service layer:

* `create_run_from_upload(..., dataset="tep")` runs the same unified RCA engine.
* `RunDetail` exposes root-cause candidates and support graph.
* `review_targets` includes:
  * `path`
  * `edge`
  * `entity_link`
  * `correction`
  * `root_cause_candidate`

Web layer:

* analysis detail shows:
  * root-cause candidate ranking
  * path/support graph explanations
  * top affected variables
  * provenance
  * feedback actions

### Stage 9: Evaluation

TEP evaluation should live under `kgtracevis.metrics` or `kgtracevis.workflows.tep_rca.evaluation`.

Metrics:

* top-k root-cause accuracy
* MRR
* path hit rate
* hit rate by fault
* hit rate by scenario/run

Important claim boundary:

* TEP fault labels are evaluation references for simulated faults.
* Runtime RCA outputs remain candidate explanations, not causal proof.

## Migration Phases

### Phase A: Bridge Mode Inside The Unified Contract

Purpose: get current KGTraceVis to show TEP route2 quickly.

Implement:

* Pydantic route2 models.
* `TepRcaArtifactProvider`.
* Parse configured TEP_KG artifacts.
* Match by `case_id` / `scenario_id`.
* Map TEP_KG ranking rows into `ranked_root_causes`.

Pros:

* fast
* validates output contract
* keeps UI/service work moving

Cons:

* still depends on external artifacts
* not fully reproducible inside KGTraceVis

### Phase B: Native RBC

Purpose: move TEP contribution extraction into KGTraceVis.

Implement:

* TEP dataset/window loader.
* fault-free profile generation/cache.
* contribution vector extraction.
* tests with tiny CSV fixtures.

Bridge artifacts become optional fixtures/reference outputs.

### Phase C: Native Propagation Scoring Strategy

Purpose: remove dependency on TEP_KG ranking outputs.

Implement:

* propagation graph view over KGTraceVis KG/Neo4j.
* candidate enumeration.
* root score/ranking score as a `ProcessPropagationScoringStrategy`.
* support subgraph extraction.
* relation-family parameter config.

At this point KGTraceVis can run TEP RCA end-to-end.

### Phase D: Native Evaluation And Reports

Purpose: make TEP RCA reproducible as KGTraceVis experiment workflow.

Implement:

* fault label reference loader.
* hit-rate/MRR/path-hit reports.
* output manifests under `runs/` or `outputs/`.
* docs explaining claim boundary.

### Phase E: Web UX And Feedback

Purpose: expose unified RCA analysis.

Implement:

* one root-cause ranking surface with scoring-method badges/details.
* review targets for TEP candidates.
* optional what-if rerun using native workflow.

## Module Boundary Decisions

### What Becomes General

* evidence schema
* KG graph loading/snapshot
* entity linking
* consistency/correction
* path ranking
* analysis envelope
* run persistence
* feedback target schema
* ranking metrics primitives

### What Stays TEP-Specific

* XMEAS/XMV mapping
* fault-free profile and RBC extraction
* relation-family propagation parameters
* Root-KGD candidate roles and anchor adjustments
* TEP fault label evaluation assumptions

### What Should Not Be Unified

* MVTec image morphology logic and TEP process propagation logic should not be forced into one algorithm.
* KG construction and RCA inference should remain separate pipelines connected by a versioned KG snapshot.
* Root-cause labels should not be inserted into evidence as observed fields.

## Minimal First Implementation Slice

If implementation starts now, the smallest useful slice is:

1. Add unified RCA result models: `RcaCandidate`, `RankedRootCause`, `RcaRankingResult`.
2. Keep `top_k_paths` as a compatibility path-oriented projection.
3. Add bridge provider that maps TEP RCA artifacts into unified `ranked_root_causes`.
4. Add `KGTracePipeline.analyze(...)` support for selecting an RCA scoring strategy.
5. Add tests with tiny TEP RCA fixture files.
5. Add one script:

```bash
uv run python scripts/run_tep_rca.py --evidence data/examples/tep_example.json --tep-rca-artifacts <fixture-or-run-dir>
```

This proves the unified contract before migrating native RBC and Root-KGD internals.
