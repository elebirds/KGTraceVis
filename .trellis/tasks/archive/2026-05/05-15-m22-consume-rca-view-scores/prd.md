# M22 Consume RCA View Scores In Path Ranking

## Goal

Make the runtime path ranking layer consume RCA view metadata produced by KG
construction. RCA score components should improve ranking/explanation when a
candidate KG overlay contains them, while legacy seed KG files still work.

## Scope

- Inspect current path ranking implementation and tests.
- Use optional `KGEdge.rca_score`, propagation metadata, or `edge_weight` when
  scoring paths.
- Keep existing relation-weighted score shape and backwards compatibility.
- Return/serialize enough score component information for review.
- Add focused tests with candidate construction-style edges.

## Non-Goals

- Do not replace the existing root-cause algorithm.
- Do not require Neo4j.
- Do not infer new facts or auto-review KG candidates.

## Acceptance

- A path with stronger RCA score metadata ranks above an otherwise similar path.
- Legacy edges without RCA score metadata keep the old behavior.
- Full tests, examples, and RCA-KG smoke remain green.
