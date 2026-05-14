# Native TEP RCA provider slice

## Decision

The next implementation slice should add a KGTraceVis-native `RootCauseProvider` for TEP instead of expanding the artifact bridge.

The provider should live under `src/kgtracevis/workflows/` or a similarly reusable `src/kgtracevis/` module, not in scripts or service handlers. The service and app should continue to call `KGTracePipeline`; provider selection/configuration can be layered later.

## Inputs

* `Evidence` with `dataset="tep"`.
* TEP variable evidence from:
  * raw evidence `extra.variables`,
  * raw evidence `extra.variable_contributions`,
  * observation metadata or values,
  * existing linked entities/top-k paths when useful.
* `KnowledgeGraph` scoped to shared + tep.

## Output

Unified `RankedRootCause` entries. These should be indistinguishable from artifact-bridge candidates to service/Postgres/dashboard consumers except for `scoring_method`.

## First-pass scoring

Use a deterministic formula with transparent score components:

```text
score = alpha * evidence_match + beta * graph_confidence + delta * propagation_support - gamma * path_length
```

This is intentionally lighter than full TEP_KG Root-KGD. The first pass proves the architecture boundary and creates a native, testable hook for later RBC/propagation refinements.

## Constraints

* Do not add industrial facts in code.
* Do not hard-code `/Users/hhm/code/TEP_KG` or `/Users/hhm/code/RootLens`.
* Do not create a TEP-specific pipeline route.
* Do not require Neo4j for unit tests.

## Relevant previous research

* `.trellis/tasks/archive/2026-05/05-14-tep-rca-integration-research/research/current-state.md`
* `.trellis/tasks/archive/2026-05/05-14-tep-rca-integration-research/research/unified-pipeline-design.md`
