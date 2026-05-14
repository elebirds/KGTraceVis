# brainstorm: compare KGTraceVis and RootLens merge strategy

## Goal

Compare `/Users/hhm/code/KGTraceVis` with `/Users/hhm/code/RootLens`, identify overlapping
and complementary responsibilities, and recommend the safest merge strategy for the paper
project without losing TEP-specific RCA assets or KGTraceVis reproducibility guarantees.

## What I already know

* KGTraceVis is the current Python package and service-oriented research pipeline:
  producers/adapters -> Evidence -> KGTracePipeline -> API/dashboard.
* KGTraceVis currently has stronger tested backend assets for MVTec and WM811K, and only
  demo-scale TEP support.
* RootLens is a Vue 3 + TypeScript + Vite prototype. Its docs position it as an integration
  shell over TEP_KG and KGTraceVis.
* RootLens has generated runtime artifacts with 107 cases: 101 TEP, 3 MVTec, 3 wafer.
* RootLens generated report records route2 exact parity against upstream TEP_KG artifacts
  for 100 route2-enabled cases.
* Local `/Users/hhm/code` contains KGTraceVis, RootLens, and panoptes, but no local TEP_KG
  checkout was found.
* RootLens scripts hard-code old upstream paths under `/Users/bytedance/my_project/...`.
* RootLens browser fallback reasoning is heuristic; its docs state the stronger semantic
  path is offline generated runtime using KGTraceVis route1 and TEP_KG route2 artifacts.

## Assumptions (temporary)

* The intended final paper codebase should remain centered on KGTraceVis unless the team
  explicitly wants a frontend-first repository.
* TEP_KG artifacts or code can be obtained later from the collaborator or exported into
  portable files.
* We should not merge two frontend stacks wholesale.

## Open Questions

* Which repository should be the single source of truth for the final paper artifact?

## Requirements (evolving)

* Preserve KGTraceVis producer/adapter/evidence/KG pipeline contracts.
* Preserve RootLens/TEP route2 parity information and TEP runtime case format.
* Avoid copying browser-only heuristic reasoning into the authoritative backend path.
* Parameterize or artifact-ize all external upstream paths before any merge.
* Keep generated runtime/data artifacts out of source unless intentionally curated.

## Acceptance Criteria (evolving)

* [ ] Produce a clear comparison of project contents and methods.
* [ ] Recommend a best merge route with staged steps.
* [ ] Identify assets to keep, rewrite, or discard.
* [ ] Identify immediate blockers and validation checks.

## Definition of Done

* No code implementation required for this analysis turn.
* If follow-up implementation begins, add/update tests and docs for merged contracts.

## Out of Scope

* Directly merging code in this turn.
* Recreating TEP_KG from unavailable upstream code.
* Treating MVTec/WM811K plausible paths as verified root-cause labels.

## Technical Notes

* Inspected KGTraceVis README, pyproject, project design, service/API contracts, dashboard
  types, KG CSV/reference files, and TEP adapter references.
* Inspected RootLens README, package, system design, module docs, scripts, runtime contracts,
  generated runtime report, generated graph snippets, and local reasoning implementation.
* RootLens `npm test` did not run because `vitest` was unavailable; likely dependencies are
  not installed in `/Users/hhm/code/RootLens`.
