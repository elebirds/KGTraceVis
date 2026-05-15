# M21 Review Queue RCA Impact Prioritization

## Goal

Make the review queue better reflect RCA impact after M19/M20. High-scoring
propagation edges, semantic derived edges, and source-grounded causal/root
cause candidates should appear with clearer priorities, reasons, and graph
impact text.

## Scope

- Use `rca_score`, propagation metadata, relation family, and semantic-derived
  provenance when assigning review priorities.
- Add clearer `graph_impact` and `recommended_action` text.
- Keep deterministic ordering.
- Preserve existing review item schema and service compatibility.
- Add focused tests.

## Non-Goals

- Do not add a UI.
- Do not auto-accept high-score edges.
- Do not run an RCA algorithm inside queue generation.

## Acceptance

- High RCA score propagation edges sort ahead of lower impact support edges.
- Semantic derived edges are explicitly reviewable and explain their source
  edge provenance.
- All construction smokes remain green.
