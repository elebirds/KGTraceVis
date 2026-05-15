# brainstorm: RootLens chapter 4 handoff document

## Goal

Create a paste-ready handoff document for WebGPT Pro to draft and refine Chapter 4, `Evidence-Centered RCA Framework`, of the RootLens ChinaVis 2026 paper. The handoff should explain the implemented KGTraceVis pipeline clearly enough that WebGPT can write from source-grounded system facts instead of inventing architecture.

## What I Already Know

* The target paper is `RootLens: Visual Analytics for Multi-Source Industrial Anomaly Detection and Traceable Root-Cause Analysis`.
* The requested section is Chapter 4: `sections/04-evidence-centered-rca-framework`.
* The user supplied a prior `Related Work` handoff as the writing-style reference.
* KGTraceVis currently implements a producer-to-evidence-to-reasoning pipeline:
  `raw/model inputs -> producers -> records -> adapters -> Evidence JSON -> KGTracePipeline -> linking/consistency/correction/path ranking/RCA`.
* Adapters are evidence-only. They must not emit root causes, ranked paths, or prefilled `kg_analysis`.
* `KGTracePipeline` owns entity linking, KG consistency checking, correction candidates, and scenario-aware RCA reasoning.
* TEP uses `TepRootKgdRcaProvider` as the single supported native TEP RCA reasoner; non-TEP cases fall back to generic relation-weighted graph path reasoning.
* KG construction is implemented as a separate source-grounded supply layer with sources, extractors, draft KG rows, manifest output, review status, and eventual Neo4j publication.
* RootLens dashboard documentation frames the UI as a consumer of run detail, evidence, paths, source edge provenance, review targets, and KG Studio review state.

## Assumptions

* The immediate deliverable should be a Markdown handoff document in the repo rather than direct edits to the LaTeX section.
* The document should be optimized for WebGPT Pro drafting Chapter 4, not for final citation verification.
* The handoff should be conservative about paper claims, especially for MVTec and WM811K/wafer RCA boundaries.

## Open Questions

* Confirm whether the generated handoff should also be copied back next to the WeChat-supplied `Handoff.md`, or whether the repo copy is sufficient.

## Requirements

* Mirror the mentor handoff style: task, expected output, constraints, paper identity, section role, implementation facts, writing outline, claim boundaries, and final prompt.
* Focus on Chapter 4 implementation: unified evidence representation, source-grounded KG construction, entity linking, consistency/correction, RCA reasoner contract, path ranking, provenance/feedback compatibility, and scenario boundaries.
* Use actual repo paths and implemented modules as source material.
* Distinguish current implementation from future extensions.
* Preserve KGTraceVis project rules: no unsupported industrial causal claims, LLMs as candidate extractors only, MVTec not RCA ground truth, adapters not RCA providers.

## Acceptance Criteria

* [ ] A paste-ready Markdown handoff exists under `docs/`.
* [ ] The handoff names concrete modules/files that WebGPT can treat as implementation anchors.
* [ ] The handoff gives a reviewer-facing Chapter 4 outline and recommended technical wording.
* [ ] The handoff includes “claims to avoid” and “safe wording” for paper drafting.
* [ ] The final response points the user to the generated file.

## Definition of Done

* Handoff document written.
* No code behavior changed.
* No generated experiment output added.

## Out of Scope

* Editing `paper/sections/04-evidence-centered-rca-framework.tex`.
* Running paper experiments.
* Verifying bibliography metadata.
* Creating figures or diagrams for the paper.

## Technical Notes

* Mentor reference: `/Users/hhm/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_pfqg4a151odu21_9574/msg/file/2026-05/Handoff.md`
* Key docs inspected: `README.md`, `docs/project_design.md`, `docs/evidence_schema.md`, `docs/adapter_contracts.md`, `docs/source_to_kg_construction_system.md`, `docs/ontology_schema.md`, `docs/paper_experiment_protocol.md`, `docs/rootlens_dashboard.md`.
* Key modules inspected: `src/kgtracevis/schema/evidence_schema.py`, `src/kgtracevis/core/pipeline.py`, `src/kgtracevis/core/rca.py`, `src/kgtracevis/core/result.py`, `src/kgtracevis/kg/entity_linker.py`, `src/kgtracevis/kg/consistency_checker.py`, `src/kgtracevis/kg/correction_generator.py`, `src/kgtracevis/kg/path_ranker.py`, `src/kgtracevis/kg/graph.py`, `src/kgtracevis/kg_construction/pipeline.py`, `src/kgtracevis/kg_construction/models.py`, `src/kgtracevis/workflows/root_cause_provider_selection.py`, `src/kgtracevis/workflows/tep_root_kgd/__init__.py`.
