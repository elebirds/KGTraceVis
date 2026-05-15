# M20 Semantic Projection Derived Edges

## Goal

Make the semantic layer more than filtering/rewrite by adding profile-driven,
source-backed derived edge rules. Derived edges should remain auditable
candidates and preserve evidence/provenance from the source edges that produced
them.

## Scope

- Add a small two-hop derived relation rule model to RCA profiles.
- Load and manifest derived rules from JSON Domain Packs.
- Apply derived rules after semantic relation projection.
- Generate optional semantic-layer edges with conservative confidence and
  `review_status=auto`.
- Record derived edge counts and IDs in `semantic_layer_manifest.json`.
- Add focused tests for duplicate avoidance, evidence provenance, and profile
  JSON loading.

## Non-Goals

- Do not implement a full graph transformation DSL.
- Do not infer new industrial facts without source-backed input edges.
- Do not publish derived edges as reviewed facts automatically.
- Do not change TEP_KG schema into the global schema.

## Acceptance

- A profile can derive `A -R3-> C` from `A -R1-> B` and `B -R2-> C`.
- Derived edges are exported as normal candidate KG edges with source/evidence.
- Default generic/TEP builds behave as before unless a profile opts into rules.
- Full construction smoke remains green.
