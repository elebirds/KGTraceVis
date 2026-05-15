# M23 RCA Output KG Build Provenance

## Goal

Carry `kg_build_id` provenance from construction/runtime KG edges into RCA
analysis outputs. A top-k path and ranked root-cause result should identify the
KG build IDs that supported it when candidate KG construction overlays are used.

## Scope

- Add `kg_build_ids` to ranked path payloads.
- Add KG build IDs to projected ranked root-cause scoring details.
- Include KG build IDs in generic RCA reasoner metadata.
- Preserve backwards compatibility for legacy seed KG edges without build IDs.
- Add focused tests.

## Non-Goals

- Do not change Neo4j persistence schema in this slice.
- Do not require all seed KG edges to have `kg_build_id`.
- Do not publish candidates automatically.

## Acceptance

- Paths supported by construction edges expose `kg_build_ids`.
- Ranked root-cause payloads preserve the build IDs through `scoring_details`.
- Generic reasoner metadata summarizes KG build IDs for the result.
- Full test/smoke gates pass.
