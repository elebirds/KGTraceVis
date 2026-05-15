# M16: Profile-Driven Semantic Projection And RCA Scoring

## Goal

Move the next slice of RCA-KG construction from hard-coded semantic/RCA defaults toward reusable Domain Pack behavior. Profiles should define relation projection rules and RCA relation-family policies so semantic projection and RCA view construction can migrate beyond the current "filter + rewrite + default propagation" implementation.

## What I Already Know

* The current end-to-end construction pipeline is real and tested: Source -> Parser -> Extractor -> DraftKG -> Alignment -> AuditGraph -> SemanticLayer -> RCAView -> ReviewQueue -> Publish -> Diff.
* Current `semantic_projection.py` mainly keeps labels, rewrites relations, assigns relation family, and sets propagation flag.
* Current `rca_view.py` defaults `propagation_direction`, `propagation_priority`, `attenuation`, and `edge_weight` in code rather than profile policy.
* The reviewer assessment identifies this as a major remaining gap for cross-domain migration.
* We should not turn TEP_KG schema into global schema; profile/domain pack configuration should carry domain-specific policy.

## Assumptions

* This milestone should be an incremental, tested schema improvement rather than a full DSL engine.
* Existing smoke outputs should remain valid; richer profile defaults can change RCA metadata but should not break source-to-KG artifact contracts.
* Alignment materialization is a separate next milestone; this task focuses on profile + semantic projection + RCA scoring schema.

## Requirements

* Add profile-level semantic projection rules that can rewrite relations and optionally swap endpoints.
* Add profile-level RCA relation-family policy with propagation flag, direction, priority, attenuation, and edge-weight multiplier/defaulting.
* Semantic projection should apply these profile rules before converting draft relations to KG edges and should record projection provenance metadata.
* RCA view construction should consume profile family policies instead of hard-coded default priority/attenuation/edge weight logic.
* Generic and TEP profiles should declare explicit family policies.
* Tests should cover a custom profile rule that rewrites and swaps endpoints, then verifies RCA scoring metadata comes from the profile.
* Docs/spec should describe the new profile-driven policy layer.

## Acceptance Criteria

* [x] New profile dataclasses/methods support projection rules and relation-family RCA policies.
* [x] Semantic projection applies rewrite/swap rules and records projection metadata.
* [x] RCA view uses profile policy for priority, direction, attenuation, and edge weight when no explicit candidate metadata overrides it.
* [x] Existing construction smoke and full test suite pass.
* [x] Docs/spec updated.

## Definition of Done

* Tests added/updated.
* Lint, typecheck, tests, and example script pass.
* Trellis task is archived and changes are committed.

## Out of Scope

* Full YAML/JSON DSL loader for profiles.
* Materializing generic alignment edges.
* Replacing RCA ranking algorithms.
* Training or learning edge weights.

## Technical Notes

* Main files: `src/kgtracevis/kg_construction/profiles.py`, `semantic_projection.py`, `rca_view.py`.
* Tests: add focused unit coverage near KG construction pipeline/profile tests.
* Docs: `docs/rca_kg_generation_architecture.md`, `docs/kg_construction.md`, backend spec.

## Implementation Notes

* Added `SemanticProjectionRule` for relation rewrite plus optional endpoint swap.
* Added `RelationFamilyPolicy` for propagation enablement, direction, priority,
  attenuation, and edge-weight scaling.
* Semantic projection now applies profile rules and writes projection provenance
  metadata before DraftRelation -> KGEdge conversion.
* RCA view manifests now include the relation-family policy payload used for
  the emitted families.
* Added tests for profile endpoint swap, profile RCA scoring defaults, and
  explicit metadata override semantics including explicit propagation disable.
