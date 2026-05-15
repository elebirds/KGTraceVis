# M25 Candidate KG Overlay Validation Workflow

## Goal

Productize the acceptance path that proves a source-to-KG construction build can
be consumed by the runtime RCA pipeline. Add a reusable workflow and CLI that
validate candidate KG overlays by:

- loading candidate nodes/edges beside the default seed KG,
- running example evidence through `KGTracePipeline`,
- preserving runtime RCA path metadata such as `path_strength`, `rca_score`,
  source edge IDs, and `kg_build_ids`,
- running Neo4j import dry-run validation over the same overlay,
- writing a structured validation report.

## Scope

- Add reusable workflow code under `src/kgtracevis/workflows/`.
- Add a thin script client under `scripts/`.
- Support either `--build-dir` with conventional `nodes.csv` / `edges.csv` or
  explicit repeated `--kg-node-path` / `--kg-edge-path`.
- Keep source-to-KG construction separate: validation must not rebuild KG, run
  extraction, mutate reviews, or publish to Neo4j.
- Update docs/spec and focused tests.

## Acceptance

- The CLI can validate a toy build directory and write
  `kg_overlay_validation_report.json`.
- The report includes example case summaries, runtime path metadata,
  `kg_backend=explicit_seed_overlay`, import dry-run counts, and input artifact
  paths.
- Tests cover workflow and CLI behavior.
- Existing full quality gates pass.
