# brainstorm: source-to-KG construction runtime workflow

## Goal

Turn the source-to-KG construction pipeline from a CLI-oriented artifact builder
into a reusable runtime workflow that service handlers and KG Studio can call.
The workflow should accept registered source inputs, execute pluggable
extractors, emit draft rows and KG CSV artifacts, write a construction manifest,
and expose the result through a stable API shape for review and later
publication.

## What I Already Know

* The previous task added the source-to-KG construction methodology, draft IR,
  extractor registry, TEP semantic-lift importer, TEP variable-mapping importer,
  `scripts/build_source_kg.py`, overlay import validation, and construction
  manifest DTOs.
* Current KG Studio can read legacy candidate KG directories and the new
  `nodes.csv` / `edges.csv` / `kg_construction_manifest.json` source-to-KG
  build shape.
* Existing service routes include `/api/kg/studio`, `/api/kg/source-draft`, and
  `/api/kg/drafts`.
* Current service storage defaults to Postgres for runs and feedback, but KG
  construction sources/drafts/builds are not yet modeled as a runtime workflow
  or service API.
* Earlier unrelated TEP RCA provider selection changes existed in the working
  tree; this task avoided making them part of the source-to-KG runtime scope.

## Assumptions

* MVP should be backend-first: reusable workflow + API route + tests.
* The first implementation should stay file-backed for construction artifacts
  and manifests, while preserving DTOs that can later map to Postgres tables.
* No live LLM extraction, AST extraction, RootLens ranking merge, or full
  frontend implementation in this task.
* Existing KG Studio frontend can consume incremental payload additions later;
  this task should avoid broad UI changes unless a small route contract needs
  support.
* Candidate publication to Neo4j remains an explicit import/dry-run action, not
  automatic background mutation.

## Requirements

* Add a reusable workflow under `src/kgtracevis/workflows/` for source-to-KG
  construction runs.
* The workflow should wrap `run_kg_construction`, write candidate artifacts, and
  return a typed result/envelope with output paths and manifest summary.
* Add service/API request and response models for starting a construction build
  from supported source inputs.
* Add a FastAPI route that can trigger the workflow for supported source types.
* Ensure KG Studio can discover the configured output directory after a build.
* Preserve source/evidence/confidence/review status and candidate-only claim
  boundaries.
* Keep CLI behavior compatible; scripts should delegate to reusable workflow if
  practical.
* Add focused tests for the workflow and API route, including a minimal
  structured/manual source case and a TEP-style fixture case if cheap.

## Acceptance Criteria

* [x] A source-to-KG workflow module exists under `src/kgtracevis/workflows/`.
* [x] `scripts/build_source_kg.py` delegates to the workflow or shares the same
      workflow helper logic.
* [x] A service route can run a construction build and returns manifest/output
      paths.
* [x] Generated artifacts include `nodes.csv`, `edges.csv`,
      `kg_construction_summary.json`, and `kg_construction_manifest.json`.
* [x] KG Studio can inspect the latest runtime build directory supplied by the
      workflow or route.
* [x] Tests cover workflow success, output protection/overwrite behavior, API
      route behavior, and existing CLI compatibility.
* [x] Lint, type-check, and relevant tests pass.

## Definition of Done

* Tests added/updated for workflow/API behavior.
* `uv run --extra dev ruff check .`
* `uv run --extra dev mypy src tests scripts`
* Relevant pytest suite passes; run full pytest if the change touches shared
  service/workflow contracts.
* Docs updated if commands or API behavior change.
* No unrelated TEP RCA provider selection files are staged or committed.

## Out of Scope

* Full frontend Source Library / Draft Review / Publish UX.
* Live LLM extraction APIs.
* AST/code extraction from TEP or RootLens source files.
* Automatic Neo4j publication from source upload.
* Large Postgres migration for KG construction tables.
* New industrial facts or curated KG edges.

## Technical Notes

* Prior methodology docs:
  * `docs/source_to_kg_construction_system.md`
  * `docs/kg_construction.md`
  * `docs/tep_kg_merge_assessment.md`
* Existing construction modules:
  * `src/kgtracevis/kg_construction/draft.py`
  * `src/kgtracevis/kg_construction/extractors.py`
  * `src/kgtracevis/kg_construction/models.py`
  * `src/kgtracevis/kg_construction/pipeline.py`
  * `src/kgtracevis/kg_construction/tep_import.py`
* Existing service surfaces:
  * `src/kgtracevis/service/api.py`
  * `src/kgtracevis/service/kg_source_drafts.py`
  * `src/kgtracevis/service/kg_drafts.py`
  * `src/kgtracevis/service/kg_studio.py`
* Existing script:
  * `scripts/build_source_kg.py`
* Relevant specs:
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/workflow-architecture.md`
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/quality-guidelines.md`
