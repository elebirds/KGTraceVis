# brainstorm: RCA KG construction acceptance smoke

## Goal

Add a reusable smoke workflow and CLI that validates the two target RCA-KG construction paths: a toy generic structured Source Library build, and an optional TEP_KG semantic/variable/RCA build.

## What I already know

* The user asked final acceptance to run at least two paths: Toy generic RCA KG and TEP RCA KG.
* `build_source_kg.py` can now build from Source Library manifests and TEP artifact inputs.
* The construction workflow already writes all core artifacts, including source library, draft, audit, semantic, RCA view, review queue, publish, summary, and construction manifest files.
* TEP_KG lives outside this repository in some environments, so the smoke should accept an explicit root/path and be skippable unless required.

## Requirements

* Add reusable smoke workflow under `src/kgtracevis/workflows/`.
* Add CLI under `scripts/` that calls the workflow and prints JSON summary.
* Toy path must create a structured source, load it through Source Library, and verify required artifacts.
* TEP path must accept a TEP_KG root, derive semantic lift, variable mapping, and RCA graph artifact paths, then verify required artifacts and RCA metadata preservation.
* Support `--require-tep` so CI/local acceptance can fail if TEP artifacts are missing.
* Add tests with temporary TEP fixtures.
* Update docs/spec with the smoke command.

## Acceptance Criteria

* [x] Smoke CLI builds Toy generic RCA-KG from a Source Library manifest.
* [x] Smoke CLI builds TEP RCA-KG from fixture TEP_KG artifact paths.
* [x] Smoke summary records required artifact paths and pass/skip status per path.
* [x] `--require-tep` fails when TEP artifacts are missing.

## Implementation Notes

* Added `src/kgtracevis/workflows/kg_construction_smoke.py` with
  `KGConstructionSmokeConfig`, `KGConstructionSmokeResult`, and
  `run_kg_construction_acceptance_smoke(...)`.
* Added `scripts/smoke_rca_kg_construction.py` as a thin CLI wrapper.
* Toy path creates a structured CSV source, registers it through a generated
  Source Library manifest, runs the construction workflow, and verifies all
  required artifacts.
* TEP path derives semantic lift, variable mapping, and RCA graph inputs from
  `--tep-kg-root`, verifies all required artifacts, and checks that
  `FaultAnchor`, `FAULT_SOURCE`, and `propagation_enabled` metadata survive.
* Added unit and CLI smoke tests with temporary TEP fixtures.
* Real local smoke against `/Users/hhm/code/TEP_KG` passed: toy path passed;
  TEP path produced 173 nodes, 285 edges, 16 FaultAnchor nodes, 159 propagation
  edges, and 63 FAULT_SOURCE edges.
* Verification: focused smoke tests `3 passed`; full pytest `317 passed`;
  `run_examples.py`, full ruff, and full mypy passed.

## Definition of Done

* Focused smoke tests pass.
* Ruff and mypy pass for touched modules.
* Full pytest and run_examples pass before archiving if feasible.
* Docs/spec updated for the acceptance smoke command.

## Out of Scope

* Neo4j write execution.
* Real LLM extraction.
* Full external TEP_KG dataset verification in unit tests.

## Technical Notes

* Relevant specs read: backend workflow architecture, database/RCA KG construction artifact contract, quality guidelines, shared cross-layer/code reuse guides.
