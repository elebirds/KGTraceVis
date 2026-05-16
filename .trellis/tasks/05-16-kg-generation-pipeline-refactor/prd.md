# brainstorm: refactor KG generation pipeline using KGBuilder comparison

## Goal

Refactor KGTraceVis KG generation around the simpler, more usable KGBuilder pipeline. The immediate goal is to understand why the current KGTraceVis source-to-KG stack became complex but hard to use, especially where default TEP subgraphs or seed layers interfere with candidate KG validation and runtime analysis.

## What I already know

* The user created `~/code/KGBuilder` as a simpler KG generation project that is currently more usable than the in-repo KGTraceVis pipeline.
* KGTraceVis keeps KG construction, material handling, source upload, review queues, publication snapshots, overlay validation, and runtime default KG loading in separate but intertwined paths.
* KGTraceVis default graph loading includes `data/kg/nodes.csv`, `mvtec_nodes.csv`, `tep_nodes.csv`, and `wafer_nodes.csv`, plus corresponding edge layers. This makes default seed content global unless a caller explicitly opts out.
* KGTraceVis adapter pipeline overlays append custom node/edge paths to default KG paths, so “KGBuilder overlay” runs are not truly KGBuilder-only unless a separate validation/runtime mode is used.
* KGBuilder exposes a six-step linear CLI: materials -> chunks -> knowledge cards -> entities -> edges -> exports/QA/profile/runtime views.
* KGBuilder separates the canonical reusable RCA-KG from the TEP Root-KGD runtime projection. TEP-specific runtime assets are generated as a separate view and seeded by a versioned JSON profile file.

## Assumptions (temporary)

* The refactor should not copy KGBuilder wholesale, but it should preserve KGBuilder's strongest property: the bypass is allowed to start from a clean design instead of remaining backward compatible with the current KG construction internals.
* The first deliverable should be an artifact protocol and migration plan before broad code changes.
* The default TEP interference problem is primarily a graph-loading and runtime-scope problem, not only an extraction-quality problem.
* The preferred direction is not an immediate replacement. Build a bypass branch first: preserve KGTraceVis platform boundaries where they help, adopt KGBuilder's simple generation path where it is clearer, validate results, then delete or retire old paths only after evidence improves.
* Compatibility with current KG construction APIs is explicitly lower priority than simplicity, reproducibility, and clean artifact boundaries.

## Decisions

* Use an artifact-protocol-first strategy, then implement a KGTraceVis-native KGBuilder-style LLM generation path. KGBuilder remains the reference implementation and comparison baseline, not the long-term runtime dependency.
* The production compiler path is LLM-only and follows KGBuilder's cards -> entities -> edges stages. Deterministic explicit relation parsing is allowed only as KGBuilder-style source-note augmentation, not as a separate simplified generation mode.
* Source handoff uses KGBuilder-compatible character chunking defaults (`chunk_size=8000`, `chunk_overlap=800`) before LLM extraction, while preserving KGTraceVis source span and content hash metadata.
* The bypass must make construction/runtime boundaries explicit instead of appending generated artifacts into default KG layers by accident.
* KGTraceVis platform responsibilities stop at standardized source units/chunks. The simplified generator starts from those units and owns knowledge cards, canonical entities, canonical edges, domain profiles, and scenario runtime views.
* Lock a complete artifact chain conceptually, but allow first implementation to mark expensive downstream artifacts as `not_generated`: source units/chunks, knowledge cards, canonical entities, canonical edges, domain profiles, KGTraceVis CSVs, scenario runtime views, and validation reports.
* The bypass is not required to maintain compatibility with existing `kg_construction` internals, DTOs, DraftKG alignment, service endpoints, or historical artifact names. It may introduce a new clean namespace and command path.
* Name the clean bypass `source_kg_compiler`, with a CLI entrypoint shaped like `scripts/compile_source_kg.py`. The name should communicate source-units-to-KG-artifacts compilation rather than patching the old construction pipeline.

## First Implementation Slice

The first slice must create an independently runnable compiler loop that can be evaluated without default KG contamination.

Required generated artifacts:

* `source_units.jsonl`: standardized platform-to-compiler handoff.
* `knowledge_cards.jsonl`: KGBuilder-style reusable semantic cards with `source_unit_id`, scenario, claim, entities mentioned, relation hints, and evidence text.
* `entities.jsonl`: canonical reusable entities with stable ids, type/label, aliases, scenario, description, and source card references.
* `edges.jsonl`: canonical reusable KG edges with stable ids, source/target ids, relation, scenario, evidence, source card references, confidence, weight, review status, and feedback counters.
* `domain_profiles.json` and `domain_profile_report.json`: KGBuilder-style reusable reasoning profiles extracted by LLM and merged with deterministic edge-derived profile rows.
* KGTraceVis-compatible `nodes.csv` and `edges.csv`: strict runtime/import CSV contract outputs.
* `qa_report.json`: artifact-level QA for schema validity, endpoint validity, duplicate/self edges, isolated nodes, required field coverage, and scenario counts.
* `validation_report.json`: runtime/evaluation validation run in strict generated-only mode, with default KG layers excluded.

First-slice placeholder artifacts:

* `domain_profiles/manifest.json` records the generated domain profile artifact path.
* `runtime_views/manifest.json` may mark scenario runtime views, including TEP Root-KGD view, as `not_generated`.
* Placeholder manifests should explain what inputs are missing and how later slices will generate them.

## Validation And Performance Gates

The first implementation should be judged against KGBuilder as the baseline, not only against the old KGTraceVis pipeline.

Isolation gate:

* Strict generated-only validation must prove it did not load default KG layers such as `data/kg/tep_*`, `data/kg/wafer_*`, or `data/kg/mvtec_*`.
* `validation_report.json` must list every KG node/edge file loaded for runtime validation.

Artifact quality gate:

* `qa_report.json` must have zero errors for schema validity, required fields, edge endpoint validity, self edges, and required provenance fields.
* Warnings such as isolated nodes are allowed in first slice if reported explicitly.

Scenario usefulness gate:

* MVTec and wafer anomalous validation cases should produce at least one candidate path when relevant source material exists.
* TEP first slice may validate canonical KG artifacts and CSV contracts without requiring Root-KGD metrics while `runtime_views/manifest.json` is `not_generated`.

Performance and portability gate:

* Runtime, number of LLM calls, prompt/input token volume where available, output artifact sizes, and source-unit/card/entity/edge counts must be recorded in `validation_report.json` or an adjacent metrics section.
* On comparable input materials and model settings, the first usable `source_kg_compiler` path should be close to KGBuilder performance and should not be materially slower or more expensive without a documented reason.
* The compiler must remain domain-portable: scenario-specific logic belongs in optional profile/runtime-view layers, not in the core source-units -> cards -> entities -> edges loop.
* Reproducibility matters as much as raw speed: deterministic ids, stable output ordering, explicit model/config metadata, and source hashes are required.

## Requirements (evolving)

* Define an explicit boundary between KG construction outputs and KG runtime seed/default loading.
* Add or standardize a “strict generated KG only” validation/runtime path so default TEP seed layers cannot silently mix into overlay experiments.
* Preserve KGTraceVis CSV contracts: node and edge schema, source/evidence/confidence/review fields, and feedback counters.
* Keep scenario-specific runtime views, especially TEP Root-KGD, as explicit projections rather than implicit default graph layers.
* Prefer small, testable steps and deterministic artifacts over hidden Python constant tables.
* Preserve useful KGTraceVis platform assets: material registration, manifests, source provenance, extraction records, and review/publish metadata where they add traceability.
* Keep the bypass easy to run as a single reproducible command or workflow, closer to KGBuilder's `main.py` shape than the current multi-surface service workflow.
* The CLI must construct an OpenAI-compatible LLM client from env/arguments and refuse to run without an LLM client, so tests and users do not accidentally validate a non-KGBuilder deterministic path.
* Define a `source_units`/`chunks` artifact as the handoff from platform to generator. Each unit should include at least source id, scenario, material path or registry reference, content text, stable chunk/unit id, source span or page/row metadata where available, content hash, and extraction/parser metadata.
* Do not feed the new bypass from existing `DraftKG` as its primary contract; that would inherit the current alignment/projection complexity too early.
* Use new artifacts and names when that keeps the path simpler; avoid adapter layers whose only purpose is to satisfy old construction internals.
* Keep backward compatibility only at deliberate external seams: KGTraceVis CSV import contracts, evidence/runtime evaluation entrypoints used for validation, and source provenance fields required by the paper/demo.
* Put new compiler code in a clean namespace, likely `src/kgtracevis/source_kg_compiler/`, rather than extending `src/kgtracevis/kg_construction/`.

## Acceptance Criteria (evolving)

* [ ] Document the current KGTraceVis vs KGBuilder pipeline differences with file-level evidence.
* [ ] Identify root causes for current KGTraceVis unusability and default TEP interference.
* [ ] Propose a staged refactor plan with a low-risk first implementation slice.
* [ ] Add tests or smoke checks that fail if default KG layers are included in strict generated-only validation/runtime mode.

## Definition of Done (team quality bar)

* Tests added/updated where behavior changes.
* `uv run --extra dev pytest` passes, or any inability to run it is recorded.
* `uv run python scripts/run_examples.py` passes, or any inability to run it is recorded.
* Docs/notes updated if user-facing KG construction behavior changes.
* Rollout/rollback considered because KG defaults affect experiments and demos.

## Out of Scope (explicit)

* Replacing Neo4j import/runtime behavior in the first pass.
* Treating KGBuilder LLM outputs as reviewed ground truth.
* Shipping a second rules-only KG construction pipeline as a replacement for KGBuilder's LLM process.
* Expanding the industrial KG with unsupported causal facts.
* Rewriting the dashboard or KG Studio UI before the construction/runtime boundary is fixed.
* Maintaining compatibility with the current KG construction internal pipeline for its own sake.
* Incrementally deleting or modifying the old pipeline before the bypass has better validation evidence.

## Technical Notes

* KGTraceVis default graph paths are defined in `src/kgtracevis/kg/graph.py`.
* KGTraceVis source-to-KG orchestration is centered in `src/kgtracevis/kg_construction/pipeline.py`, `src/kgtracevis/workflows/source_kg_construction.py`, and `src/kgtracevis/service/kg_construction.py`.
* KGTraceVis adapter runs append custom KG paths to defaults in `src/kgtracevis/experiments/adapter_pipeline.py`.
* KGTraceVis overlay validation has opt-out flags for defaults, but the normal overlay path includes defaults unless explicit flags are passed.
* KGBuilder's main pipeline lives in `~/code/KGBuilder/main.py`.
* KGBuilder profile extraction lives in `~/code/KGBuilder/domain_profile_extractor.py`.
* KGBuilder TEP Root-KGD projection lives in `~/code/KGBuilder/tep_root_kgd_projector.py`.
* Rough size comparison from initial scan: KGTraceVis KG/service/workflow source-related surface has dozens of files, while KGBuilder has a small top-level Python toolchain. Key KGTraceVis files inspected total thousands of lines across pipeline/workflow/service, while KGBuilder's main orchestration is about one hundred lines.
