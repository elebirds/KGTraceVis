# M30 TEP Runtime Overlay Acceptance Diagnostics

## Goal

Close the audit gap between TEP construction acceptance and TEP runtime RCA
acceptance. The TEP construction smoke already proves that TEP candidates,
propagation metadata, and fault anchors are exported, but the Root-KGD runtime
provider currently reads static assets and does not preserve candidate overlay
`kg_build_id` / edge provenance in its RCA paths.

## Scope

- Keep the TEP Root-KGD scoring algorithm unchanged.
- When a runtime `KnowledgeGraph` contains candidate overlay edges whose
  `external_edge_id` matches Root-KGD static edge IDs, enrich Root-KGD
  `source_edges`, `source_edge_ids`, and `kg_build_ids` with that candidate
  provenance.
- Keep enrichment read-only: the reasoner must not mutate KG data or decide
  reviewed facts.
- Add focused tests proving TEP provider path/candidate outputs preserve overlay
  provenance.
- Add or extend smoke/validation assertions so TEP runtime contribution can be
  reported by the same contribution-aware contract.

## Non-Goals

- Do not replace Root-KGD runtime assets with constructed KG artifacts.
- Do not make TEP_KG schema the global runtime schema.
- Do not mark TEP candidate facts as reviewed.
- Do not add a UI review layer in this task.

## Acceptance Criteria

- `TepRootKgdRcaProvider.reason_root_causes(...)` uses the passed graph for
  provenance enrichment when possible.
- Enriched TEP paths include `kg_build_ids` and `source_edge_ids` referencing
  candidate overlay rows.
- Ranked root-cause candidates preserve the same candidate supporting edge
  provenance.
- Existing Root-KGD tests still pass with an empty graph.
- Focused tests cover matched and unmatched overlay provenance.
- Full quality gates pass before commit.

## Audit Status

- Fixes the P2 audit concern that TEP construction acceptance is build-level
  only and lacks runtime-level overlay contribution proof.
- Leaves broader future work open: using constructed TEP KG as the primary
  Root-KGD runtime asset source instead of static checked-in assets.
