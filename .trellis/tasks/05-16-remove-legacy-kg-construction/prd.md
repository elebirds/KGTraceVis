# remove legacy KG construction pipeline

## Goal

Remove the old KG construction pipeline while preserving the current source KG compiler, analysis runtime, and TEP Root-KGD runtime assets.

## What I already know

* User explicitly chose direct removal because deadline is tight.
* Scope is only the old KG-building implementation.
* Do not remove `data/kg/tep_root_kgd` or Root-KGD analysis/provider/runtime assets.
* System should retain the current KG building and analysis path.
* Material/source management is still needed for front-end and back-end workflows,
  but it should feed the current source KG compiler rather than the old
  construction/review/publish implementation.

## Requirements

* Delete legacy KG construction modules/scripts/tests that are no longer part of the current source KG compiler path.
* Keep current source KG compiler and evaluation workflow intact.
* Keep analysis pipeline and TEP Root-KGD runtime intact.
* Preserve the material registry/upload/local-path APIs as platform source
  management, with extraction reduced to "compiler-ready source registration".
* Keep API-compatible construction endpoints as a thin compatibility shell over
  `source_kg_compiler`; do not keep the old DraftKG/review/publish engine.
* Expose asynchronous KG build jobs with pollable progress so API clients do not
  appear frozen during long LLM compiler runs.
* Remove imports/references to deleted legacy code.

## Acceptance Criteria

* [x] Repository no longer exposes the old KG construction pipeline as an active code path.
* [x] Current KG compiler and RCA analysis tests still pass in the relevant scope.
* [x] No default analysis path depends on removed legacy KG construction code.
* [x] Material records can still be registered/uploaded and converted into
      source compiler inputs.
* [x] KG build API clients can submit a background build job and poll compiler
      progress events.
* [x] `data/kg/tep_root_kgd` remains untouched.

## Out of Scope

* Replacing TEP Root-KGD generated assets.
* Deleting analysis modules, entity linking, consistency checking, or path ranking.
* Broad docs rewrite beyond immediate stale references if needed.
* Reintroducing old edge review/publish semantics.

## Technical Notes

* Created for direct implementation after user decision.
* Progress events come from the source KG compiler `progress_callback` and are
  persisted as JSONL under the source KG build root.
