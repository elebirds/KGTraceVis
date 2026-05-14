# brainstorm: source-to-KG construction methodology

## Goal

Define KGTraceVis's knowledge-graph construction methodology as a reusable
system, not only as CSV scripts: users manage sources, the system extracts
candidate entities and relations through pluggable extractors, users may review
or directly publish candidates, and the resulting KG is written to Neo4j for the
reasoning pipeline.

The task has now expanded from documentation into the first implementation
slice: build the reusable backend construction pipeline core and a TEP semantic
lift importer that can adapt `TEP_KG` outputs into KGTraceVis draft KG rows.

## What I already know

* The current KG is a task-oriented, source-constrained graph used for evidence
  linking, consistency checking, correction generation, path ranking, and visual
  explanation.
* Current tracked seed KG rows live under `data/kg/*.csv` and use a strict node
  and edge contract.
* Current candidate construction exists under `src/kgtracevis/kg_construction/`,
  especially `case_kg_hardening.py`, but it is not yet framed as a full product
  workflow.
* The desired system includes frontend source upload/management, LLM-assisted
  entity/relation extraction, draft KG generation, optional review, publication,
  and Neo4j writeback.
* Confidence should remain the primary trust signal. Relation names should
  express semantics, while user-controlled confidence/review status express
  reliability.
* TEP code-file extraction by AST is a future extractor class and will likely
  arrive with RootLens merge work. The methodology should reserve a pluggable
  extractor interface for it, but not implement it now.
* `/Users/hhm/code/TEP_KG` has a TEP-specific three-layer build strategy:
  `Full KG -> Semantic Lift Layer -> RCA Graph`. It should be adapted through
  extractors/importers, not copied as KGTraceVis's global schema.
* The KG construction pipeline ultimately serves the inference pipeline. It
  should produce a versioned runtime KG consumed by `KGTracePipeline`.

## Assumptions

* This task implements the backend construction core, not the full frontend,
  database schema, or Neo4j publication workflow.
* The document should cover both research-methodology language and product
  system architecture, because KGTraceVis needs both for the paper/prototype.
* CSV snapshots remain useful for reproducibility, but Neo4j is the runtime KG
  backend.
* The first implementation slice should be small enough to test locally:
  pluggable extractor registry, common draft IR, construction runner, TEP
  semantic-lift import, construction run manifests, and a CSV overlay path into
  the reasoning/import checks.

## Requirements

* Document the source-to-KG methodology with source layers, source management,
  extraction classes, candidate/draft KG objects, review modes, publication, and
  Neo4j runtime handoff.
* Explicitly describe pluggable extractors, including structured records, text
  + LLM, visual/mask geometry, wafer pattern extraction, manual tables, logs,
  and future AST/code extraction.
* Define the boundary between KG construction and KG reasoning pipelines.
* Clarify that users may skip review, but low-confidence/unreviewed knowledge
  should stay traceable and visible to downstream reasoning.
* Update existing KG/project docs so the new methodology is discoverable.
* Add a reusable draft KG IR under `src/kgtracevis/kg_construction/`.
* Add a pluggable extractor registry and construction runner.
* Add a TEP semantic-lift importer that reads `TEP_KG` semantic lift nodes/edges
  and emits KGTraceVis draft nodes/edges with `scenario=tep`.
* Add a TEP variable-mapping importer for `xmeas_*` and `xmv_*` channel/entity
  alignment.
* Add a CLI that materializes source-to-KG candidate CSV artifacts.
* Add construction run, draft-row, review-decision, build-summary, and manifest
  DTOs so scripts, services, and future storage can share one construction
  vocabulary.
* Let candidate CSV artifacts run as explicit KG overlays for examples and
  Neo4j import dry-runs before publication.
* Let KG Studio read source-to-KG build artifacts without requiring legacy
  `nodes_candidate.csv` / `edges_candidate.csv` filenames.
* Keep relation-family and propagation metadata in draft metadata so a future
  path-ranker or Neo4j publisher can use it.

## Acceptance Criteria

* [x] A dedicated methodology/system document exists under `docs/`.
* [x] `docs/kg_construction.md` points to the new document and summarizes the
      construction lifecycle.
* [x] `docs/project_design.md` mentions the construction pipeline as the
      knowledge supply layer for the reasoning pipeline.
* [x] The document names out-of-scope future implementation work, including TEP
      AST extraction and RootLens merge work.
* [x] No unsupported new industrial KG facts are added.
* [x] A TEP_KG merge assessment records reusable ideas, incompatibilities, and
      a phased integration plan.
* [x] Reusable draft KG models exist and convert to existing candidate
      entity/triple contracts.
* [x] A construction runner can execute registered extractors and produce
      validated `KGNode`/`KGEdge` rows.
* [x] A TEP semantic-lift extractor imports minimal TEP_KG-style JSONL rows.
* [x] A TEP variable-mapping extractor imports channel aliases and alignment
      relations.
* [x] A CLI can generate candidate KG CSV artifacts from supported source
      inputs.
* [x] Construction results expose a build manifest with sources, draft rows,
      summary counts, and artifact paths.
* [x] Candidate KG CSV artifacts can be appended to the default KG for
      `run_examples.py` and `import_kg.py --dry-run` validation.
* [x] KG Studio can inspect both legacy candidate KG artifacts and new
      source-to-KG build artifacts.
* [x] Focused tests cover the pipeline and TEP importer.

## Definition of Done

* Documentation is clear enough to guide later implementation tasks.
* No generated experiment artifacts are committed.
* Markdown renders with readable headings and concrete data-flow diagrams.
* Lightweight verification confirms the changed docs are present and link paths
  are reasonable.

## Out of Scope

* Implementing frontend source upload/management.
* Implementing LLM extraction APIs.
* Implementing AST extraction from TEP code files.
* Changing Postgres schemas.
* Importing Root-KGD ranking/edge-weight training into `KGTracePipeline`.
* Adding new KG edges or curated industrial facts.

## Technical Notes

* Relevant current files:
  * `docs/kg_construction.md`
  * `docs/kg_hardening_pipeline.md`
  * `docs/project_design.md`
  * `src/kgtracevis/kg/graph.py`
  * `src/kgtracevis/kg_construction/*`
  * `scripts/build_kg.py`
  * `scripts/build_case_kg.py`
  * `scripts/import_kg.py`
  * `docs/tep_kg_merge_assessment.md`
* Relevant specs read:
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/frontend/workbench-ui-guidelines.md`

## Decision (ADR-lite)

**Context**: KGTraceVis needs a repeatable way to build and update the KG from
heterogeneous materials while preserving user control and runtime Neo4j support.

**Decision**: Frame KG construction as a source-grounded, pluggable,
human-controllable construction pipeline that produces a versioned runtime KG
for the inference pipeline.

**Consequences**: The next implementation tasks can add source management,
extractor plugins, review queues, KG version metadata, and Neo4j publication in
small increments without tying the methodology to one extractor or one dataset.
