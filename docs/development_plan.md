# Development Plan

This plan turns KGTraceVis from a research skeleton into a reproducible v0 RCA
pipeline. The priority is a small, testable, source-constrained loop before
larger KG construction, Neo4j integration, or richer visualization.

## Phase 0: Environment And Baseline

Goal: make the repository reproducible on a fresh machine.

- Verify Python 3.10+ and `uv` installation.
- Run `uv run --extra dev pytest`.
- Run `uv run python scripts/run_examples.py`.
- Keep `mvtec`, `tep`, and `wafer` naming consistent across schema, examples,
  docs, and metrics.

## Phase 1: In-Memory KG V0

Goal: provide a fast, testable KG backend that does not require Neo4j.

- Load `data/kg/nodes.csv` and `data/kg/edges.csv`.
- Validate node and edge columns.
- Preserve `source`, `evidence`, `confidence`, `weight`, `review_status`, and
  feedback counters on every edge.
- Build a directed NetworkX graph for linking, consistency checks, and path
  ranking.

## Phase 2: Core Analysis Modules

Goal: make the analysis pipeline produce real RCA outputs.

- Entity linker: exact ID, exact name, alias, then fuzzy match.
- Consistency checker: compare linked evidence fields against KG constraints.
- Correction generator: suggest field replacements from KG neighborhoods.
- Path ranker: rank candidate root-cause paths by confidence, evidence match,
  and length penalty.

## Phase 3: Pipeline Wiring

Goal: make `KGTracePipeline.analyze()` run the full v0 loop.

```text
Evidence JSON
-> entity linking
-> consistency checking
-> correction candidates
-> RCA path ranking
-> AnalysisResult
```

## Phase 4: MVTec RCA Reference Layer

Goal: implement the updated paper direction.

- Select a small set of MVTec objects such as `metal_nut`, `cable`, `screw`,
  `bottle`, `capsule`, and `pill`.
- Define plausible root-cause categories.
- Curate defect / morphology / location to plausible RCA mappings.
- Store each mapping as source-constrained KG edges with review status.

## Phase 5: Metrics And Experiments

Goal: generate paper-ready numbers from reproducible scripts.

- Schema validity rate.
- Entity linking accuracy and top-k linking accuracy.
- Inconsistency detection precision / recall.
- Correction accuracy and top-k correction accuracy.
- Top-k root-cause accuracy, MRR, and path hit rate.

## Phase 6: Streamlit Demo

Goal: show the full RCA reasoning loop in a lightweight visual interface.

- Case selector.
- Raw and normalized evidence.
- Linked entities.
- Consistency score and inconsistent fields.
- Correction candidates.
- Top-k RCA paths.
- Optional what-if editing and accept/reject feedback.

## Phase 7: Neo4j And Wafer Deepening

Goal: add graph database support after the in-memory loop is stable.

- Import validated KG CSVs into Neo4j.
- Query paths through Cypher.
- Expand wafer image-log case studies when source material is available.
