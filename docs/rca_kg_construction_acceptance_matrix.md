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
| Overlay validation CLI | Accepted | `scripts/validate_kg_overlay.py --build-dir <build_dir>`; contribution accepted only when `overlay_contributed=true` |
| Overlay validation API | Accepted | `POST /api/kg/construction/builds/{run_id}/validate-overlay`; same contribution semantics |
| Review queue | Accepted | `review_queue.json`, review API, and replay workflow |
| Review-controlled publish snapshot | Accepted | `published_nodes.csv`, `published_edges.csv`, `publish_report.json` |
| Artifact diff | Accepted | fresh no-op and review replay `kg_construction_diff.json` |
| External profile packs | Accepted | `--profile-path` / `profile_path`, recorded in `profile_manifest.json` |
| LLM document extraction boundary | Accepted as controlled adapter | LLM/offline document IE emits DraftKG candidates and material audit artifacts; it does not publish facts |

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

## Boundary Checks

- LLM output is candidate DraftKG only. It remains source-grounded and
  `review_status=auto` until reviewed or policy-allowed.
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
uv run --extra dev pytest -q
uv run python scripts/run_examples.py
uv run python scripts/smoke_rca_kg_construction.py --tep-kg-root /Users/hhm/code/TEP_KG --require-tep --overwrite
uv run python scripts/validate_kg_overlay.py --build-dir runs/source_kg_smoke/material_direct --example-dir data/examples --output-path runs/source_kg_smoke/material_direct/kg_overlay_validation_report.json
```

At that pass, the test suite reported `344 passed`, and the RCA-KG construction
smoke reported four passing paths: `toy_generic`, `material_direct`,
`runtime_overlay`, and `tep`.

## Remaining Non-Goals

- Live LLM extraction quality is not certified as a final product experience.
  The productized part is the source-grounded draft, audit, review, and publish
  control loop around it.
- Neo4j real import is not run automatically in tests.
- UI review pages can consume the API/report contracts, but this matrix does
  not claim a complete human review frontend.
