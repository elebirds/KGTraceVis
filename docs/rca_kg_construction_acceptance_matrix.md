# RCA-KG Construction Acceptance Matrix

This page is the current acceptance map for the rebuilt RCA-oriented KG
construction system. It links the intended architecture to concrete code,
artifacts, commands, and guardrails.

## Accepted Main Path

The implemented construction path is:

```text
Source Library
-> Parser / Chunk
-> Extractor Registry
-> DraftKG
-> Entity Alignment
-> Source Audit Graph
-> Semantic Layer
-> RCA Reasoning View
-> Review Queue
-> Versioned Publish Snapshot
-> Runtime RCA Overlay Validation
```

The reusable implementation lives under
`src/kgtracevis/kg_construction/` and is orchestrated by
`kgtracevis.workflows.source_kg_construction`.

## Required Build Artifacts

Every source-to-KG construction build writes:

```text
nodes.csv
edges.csv
published_nodes.csv
published_edges.csv
source_library_manifest.json
draft_manifest.json
profile_manifest.json
entity_alignment_manifest.json
source_audit_graph_manifest.json
semantic_layer_manifest.json
rca_view_manifest.json
review_queue.json
review_decisions.jsonl
publish_manifest.json
publish_report.json
kg_construction_diff.json
kg_construction_summary.json
kg_construction_manifest.json
```

Runtime overlay validation additionally writes:

```text
kg_overlay_validation_report.json
```

This report is intentionally not a required construction artifact because it is
a validation product over a build and an example set, not a construction stage.
It separates `contract_validated`, `runtime_validated`, and
`overlay_contributed`. A build that loads and runs but does not appear in any
top-k RCA path is contract/runtime valid, but not overlay-contribution accepted.

## Acceptance Rows

| Capability | Current Status | Verification |
|---|---|---|
| Toy generic construction | Accepted | `scripts/smoke_rca_kg_construction.py` path `toy_generic` |
| Material direct construction | Accepted | smoke path `material_direct` |
| TEP construction import | Accepted | smoke path `tep`; preserves `relation_family`, propagation flags, and fault anchors |
| Runtime overlay RCA path | Accepted | smoke path `runtime_overlay`; checks `path_strength`, `rca_score`, `source_edge_ids`, `kg_build_ids` |
| TEP runtime overlay RCA path | Accepted | smoke path `tep_runtime_overlay`; Root-KGD paths preserve candidate overlay `kg_build_id` and source edge IDs via `external_edge_id` matching |
| Overlay validation CLI | Accepted | `scripts/validate_kg_overlay.py --build-dir <build_dir>`; contribution accepted only when `overlay_contributed=true` |
| Overlay validation API | Accepted | `POST /api/kg/construction/builds/{run_id}/validate-overlay`; same contribution semantics |
| Review queue | Accepted | `review_queue.json`, review API, and replay workflow |
| KG Studio construction review UI | Accepted | `web` build page lists construction builds, reads review queues, submits accept/reject decisions, and runs overlay validation |
| Review-controlled publish snapshot | Accepted | `published_nodes.csv`, `published_edges.csv`, `publish_report.json` |
| Artifact diff | Accepted | fresh no-op and review replay `kg_construction_diff.json` |
| External profile packs | Accepted | `--profile-path` / `profile_path`, recorded in `profile_manifest.json` |
| LLM document extraction boundary | Accepted as controlled adapter | OpenAI/offline fixture providers emit DraftKG candidates and material audit artifacts; no-key provider selection is exposed in KG Studio and does not publish facts |
| Document understanding mode | Accepted as advisory reader | `long_context` can use an OpenAI-compatible/fixture `DocumentUnderstandingClient`; `agentic` runs retrieval-backed named reader steps and records selected chunk IDs; maps guide chunk IE and cross-chunk review items but do not publish facts or relax chunk evidence grounding |
| Reviewed cross-chunk RCA opt-in | Accepted as review-only staging policy | Accepted proposals default to non-propagating, unscored reviewed edges; explicit `review_acceptance_policy`/`rca_policy` can apply capped RCA fields only after review accept and relation/family validation |
| MVTec raw-material LLM construction | Accepted as source-grounded smoke path | `scripts/build_mvtec_llm_source_pack.py` and `scripts/smoke_mvtec_llm_kg_construction.py`; excludes derived catalog/KG files, parses DS-MVTec `defects_dict` into DraftKG candidate taxonomy, includes local raw PDFs such as manufacturing root-cause references when available, and treats plausible causes as reviewable hypotheses |

## Commands

Run the full construction acceptance smoke:

```bash
uv run python scripts/smoke_rca_kg_construction.py \
  --tep-kg-root /Users/hhm/code/TEP_KG \
  --require-tep \
  --overwrite
```

Validate one build as a runtime overlay:

```bash
uv run python scripts/validate_kg_overlay.py \
  --build-dir runs/source_kg_smoke/material_direct \
  --example-dir data/examples \
  --output-path runs/source_kg_smoke/material_direct/kg_overlay_validation_report.json
```

Validate a TEP build against runtime Root-KGD overlay provenance without merging
checked-in seed nodes:

```bash
uv run python scripts/validate_kg_overlay.py \
  --build-dir runs/source_kg_smoke/tep \
  --example-dir data/examples \
  --overlay-only-runtime \
  --overlay-only-import \
  --output-path runs/source_kg_smoke/tep/kg_overlay_validation_report.json
```

Run examples with explicit candidate CSV overlays:

```bash
uv run python scripts/run_examples.py \
  --kg-node-path runs/source_kg_smoke/material_direct/nodes.csv \
  --kg-edge-path runs/source_kg_smoke/material_direct/edges.csv
```

Dry-run Neo4j import readiness for default KG plus candidate overlay:

```bash
uv run python scripts/import_kg.py \
  --include-defaults \
  --nodes runs/source_kg_smoke/material_direct/nodes.csv \
  --edges runs/source_kg_smoke/material_direct/edges.csv \
  --dry-run
```

Build and test the MVTec raw-material source path without an external key:

```bash
uv run python scripts/smoke_mvtec_llm_kg_construction.py \
  --output-dir runs/mvtec_llm_kg_smoke \
  --provider offline_fixture \
  --overwrite
```

For live model testing, use `--provider openai`. The smoke loads `.env.local`
and `.env`, sends raw/near-raw source materials through document understanding,
chunk IE, brainstorming, and review queue generation, and verifies that
published RCA-like MVTec cause edges are not created by the LLM path.

## Boundary Checks

- LLM output is candidate DraftKG only. It remains source-grounded and
  `review_status=auto` until reviewed or policy-allowed.
- The MVTec validation path must start from raw or near-raw documents, not from
  generated catalogs or prebuilt KG snapshots.
- MVTec process/root-cause PDFs may guide chunk IE through source-pack role
  metadata, but extracted edges still pass profile relation whitelists, endpoint
  label constraints, review queues, and publish policy.
- Document understanding and hypothesis brainstorming are independent axes:
  `chunk`, `long_context`, and `agentic` can be mixed with
  `hypothesis_mode=brainstorm`.
- LLM-assisted alignment, semantic policy, RCA policy, and brainstorming output
  is advisory. It may suggest, explain, rank, and create review items, but it
  cannot directly publish facts, change canonical IDs, mutate profiles, or
  enable RCA propagation.
- Brainstorming artifacts are recorded as
  `brainstorm_hypotheses.jsonl`, `brainstorm_evidence_tasks.jsonl`,
  `brainstorm_profile_gaps.json`, `brainstorm_review_items.json`, and
  `hypothesis_brainstorming_manifest.json`.
- Accepted `hypothesis_candidate`, `profile_gap_candidate`, and
  `alias_mapping_candidate` items record decisions/accepted artifacts only.
  Accepted `causal_chain_candidate` items stage reviewed edges only when every
  proposed edge validates against existing endpoints, allowed relations, and
  source spans.
- Accepted semantic/RCA policy suggestions only affect existing edges after
  whitelist checks and caps (`rca_score <= 0.7`,
  `propagation_priority <= 0.75`, `source_trust <= 0.8`). Unsupported
  relation/family suggestions are ignored or recorded as profile gaps.
- TEP_KG is integrated through TEP extractors and profile/domain-pack behavior,
  not copied into the global schema.
- TEP external `accept` does not become KGTraceVis `reviewed`.
- Generic profile now retains `FaultType`, `AnomalyType`, and `DefectType`
  nodes so structured RCA source nodes are not dropped before runtime overlay
  validation.
- Real Neo4j publication requires explicit `dry_run=false` and
  `confirm_publish=true`.
- `published_edges.csv` is policy-controlled; high-risk causal or propagation
  candidates remain pending until reviewed.

## Latest Session Gate

The latest acceptance pass in this thread ran:

```bash
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
uv run pytest -q
cd web && npm run build
uv run python scripts/smoke_rca_kg_construction.py --output-dir /tmp/kgtracevis_brainstorm_smoke --tep-kg-root /Users/hhm/code/TEP_KG --require-tep --overwrite
uv run python scripts/smoke_mvtec_llm_kg_construction.py --output-dir /tmp/kgtracevis_mvtec_offline_smoke_v2 --provider offline_fixture --overwrite
uv run python scripts/build_wafer_llm_source_pack.py --output-dir /tmp/kgtracevis_wafer_source_pack_v2 --overwrite
uv run python scripts/smoke_wafer_llm_kg_construction.py --output-dir /tmp/kgtracevis_wafer_offline_smoke_v2 --provider offline_fixture --overwrite
uv run python scripts/smoke_mvtec_llm_kg_construction.py --source-pack /tmp/kgtracevis_mvtec_source_pack_expanded/mvtec_llm_source_pack.json --output-dir /tmp/kgtracevis_mvtec_expanded_live_12k_v3 --provider openai --max-materials 6 --document-understanding-mode long_context --max-chars 12000 --overlap-chars 1200 --overwrite
uv run python scripts/smoke_wafer_llm_kg_construction.py --source-pack /tmp/kgtracevis_wafer_source_pack_v2/wafer_llm_source_pack.json --output-dir /tmp/kgtracevis_wafer_live_smoke_12k_v6 --provider openai --max-materials 2 --document-understanding-mode long_context --max-chars 12000 --overlap-chars 1200 --overwrite
uv run python scripts/evaluate_tep_rca.py --output-dir /tmp/kgtracevis_tep_rca_eval --raw-data-dir data/raw/tep --faults 1,2,6 --max-runs-per-fault 1 --max-cases 3 --overwrite
```

At that pass, the test suite reported `387 passed, 2 skipped`, and the RCA-KG
construction smoke reported six passing paths: `toy_generic`,
`material_direct`, `material_brainstorm`, `runtime_overlay`, `tep`, and
`tep_runtime_overlay`. The live MVTec expanded smoke used OpenAI-compatible
`openai` provider settings from `.env.local` / `.env`, larger 12k chunks, and
six raw/near-raw materials. It produced `187` nodes and `418` edges, including
source-backed PDF/web `HAS_PLAUSIBLE_CAUSE` and `CAUSES` candidates from
injection molding, flow-mark, and molding-flash sources, and did not publish
RCA-like cause edges. The live wafer smoke used the prioritized wafer source
pack (`wafer_defect_frontiers_2023`, `wm811k_example_records`) and produced
`23` nodes and `17` edges with `HAS_LOCATION`, `HAS_MORPHOLOGY`,
`HAS_SPATIAL_SIGNATURE`, `HAS_PLAUSIBLE_CAUSE`, and `HAS_ANOMALY` relations,
again with zero published edges. The TEP evaluation over faults 1, 2, and 6
reported top-1/top-3/top-5 root-cause accuracy, MRR, and path hit rate all at
`1.0` for the three sampled cases.

## Remaining Non-Goals

- Live LLM extraction quality is not certified as a final product experience.
  The productized part is the source-grounded draft, audit, review, and publish
  control loop around it.
- Neo4j real import is not run automatically in tests.
