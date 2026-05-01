# brainstorm: Trellis init development roadmap

## Goal

Initialize a usable Trellis planning task for KGTraceVis by recording the current
repository state, clarifying the most valuable next code tasks, and preparing
context manifests for future `trellis-implement` and `trellis-check` agents.

The output should make development proceed as a sequence of small, reproducible
tasks instead of a broad rewrite.

## What I Already Know

- KGTraceVis is a uv-managed Python research prototype for knowledge-enhanced
  industrial anomaly evidence analysis and root-cause traceability.
- The repo already contains the expected top-level structure: `configs/`,
  `src/`, `scripts/`, `data/`, `runs/`, `outputs/`, `artifacts/`, `notebooks/`,
  `docs/`, `paper/`, and `tests/`.
- Core v0 modules exist for evidence schema validation, in-memory KG loading,
  entity linking, consistency checking, correction candidate generation, path
  ranking, and pipeline orchestration.
- The in-memory pipeline is already wired through `KGTracePipeline.analyze()`.
- The current baseline is green:
  - `uv run --extra dev pytest` passed with 9 tests.
  - `uv run python scripts/run_examples.py` analyzed 3 example evidence files.
- Several modules are still one-line placeholders and should become future
  Trellis tasks rather than hidden TODOs:
  - dataset adapters under `src/kgtracevis/adapters/`
  - KG construction helpers under `src/kgtracevis/kg_construction/`
  - Neo4j import implementation under `src/kgtracevis/kg/import_neo4j.py`
  - noise injection under `src/kgtracevis/noise/noise_injector.py`
  - metrics modules under `src/kgtracevis/metrics/`
  - visualization export/helpers under `src/kgtracevis/viz/`
  - service layer under `src/kgtracevis/service/`
  - feedback store under `src/kgtracevis/feedback/feedback_store.py`
- Existing documentation already suggests a staged direction in
  `docs/development_plan.md` and `docs/implementation_research_plan.md`.
- Trellis backend guidelines have been populated under `.trellis/spec/backend/`.

## Assumptions

- The next development cycle should prioritize a paper-ready, reproducible v0
  loop over richer infrastructure.
- The in-memory KG should remain the default backend until experiments and demo
  flows are stable.
- MVTec root-cause outputs must be described as curated plausible RCA references,
  not verified factory ground truth.
- Future tasks should keep scripts/apps as clients of reusable logic under
  `src/kgtracevis/`.

## Requirements

- Record a clear current-state summary for future sessions.
- Convert the broad development plan into an ordered task path with each step
  small enough for Trellis planning, implementation, and check agents.
- Configure `implement.jsonl` and `check.jsonl` with the relevant backend spec
  context.
- Do not modify runtime code in this task unless a planning validation command
  exposes a broken baseline.

## Recommended Development Path

### 0. Close Trellis Bootstrap

Purpose: keep Trellis itself clean before more feature work.

- Confirm `.trellis/spec/backend/` files contain real project conventions.
- Archive `00-bootstrap-guidelines/` once the user is satisfied.
- Keep this roadmap task as the active planning artifact for the next code task.

Acceptance:

- Backend spec exists and is referenced by future task manifests.
- No bootstrap task remains active after explicit finish/archive.

### 1. Harden Pipeline Output Contracts

Purpose: make current v0 outputs stable enough for experiments, feedback, and
visualization.

- Review `AnalysisResult`, correction candidate IDs, path IDs, and source edge
  payloads.
- Ensure normalized output can be serialized and attached back into evidence
  without mutating raw evidence.
- Add tests around stable IDs and feedback-compatible references.

Acceptance:

- Pipeline output includes stable references for linked entities, correction
  candidates, ranked paths, and supporting KG edges.
- Existing examples still pass.

### 2. Implement Noise And Metrics V0

Purpose: enable reproducible paper experiments on clean/noisy evidence.

- Implement deterministic field-level noise injection with fixed seeds.
- Implement schema, linking, correction, RCA ranking, MRR, and path-hit metrics.
- Wire `scripts/run_noise_experiment.py` to save reproducible summaries under
  `runs/` or `outputs/`.

Acceptance:

- Tests cover deterministic corruption and metric edge cases.
- Script output records `is_noisy`, `noise_level`, `corrupted_fields`, and
  `clean_reference`.

### 3. Implement Dataset Adapter V0s

Purpose: convert small MVTec, TEP, and wafer inputs into the unified evidence
schema without creating dataset-specific schemas.

- MVTec adapter: object, defect type, optional mask-derived location/morphology,
  and raw paths/descriptions.
- TEP adapter: variable/fault evidence and variable contribution metadata.
- Wafer adapter: image/log/process event evidence with dataset-specific details
  stored in `raw_evidence.extra`.

Acceptance:

- Adapters return validated `Evidence` objects.
- Dataset-specific details remain inside `raw_evidence`.

### 4. Expand Source-Constrained KG Construction

Purpose: support curated KG growth while preserving provenance.

- Implement source loading, candidate extraction, confidence assignment, triple
  cleaning, and CSV export helpers.
- Deduplicate nodes/edges without overwriting reviewed triples automatically.
- Register sources in `data/kg/source_registry.csv` or `docs/sources/`.

Acceptance:

- Every exported edge includes source, evidence, confidence, weight,
  review_status, and feedback counters.
- Tests cover deduplication and reviewed-edge protection.

### 5. Build Streamlit Demo V0

Purpose: expose the full reasoning loop for visual analytics review.

- Case selector over `data/examples/` and later generated runs.
- Raw evidence, normalized evidence, linked entities, consistency score,
  inconsistent fields, correction candidates, and top-k RCA paths.
- Basic what-if editing and accept/reject feedback actions if feasible.

Acceptance:

- Demo calls `KGTracePipeline` instead of duplicating pipeline logic.
- The app starts locally with `uv run streamlit run src/kgtracevis/app/streamlit_app.py`.

### 6. Add Neo4j Backend After In-Memory Stability

Purpose: provide graph database import/query support once the v0 loop is stable.

- Implement Neo4j import using validated KG CSV rows.
- Keep the in-memory backend as the default for tests and local scripts.
- Add optional Neo4j example execution behind `--with-neo4j`.

Acceptance:

- Neo4j code is optional and environment-driven.
- Neo4j changes pass the extra import/example commands required by project docs.

## Out Of Scope

- No large general-purpose industrial KG.
- No unsupported causal facts or fabricated KG edges.
- No deep model training for v0.
- No dataset-specific JSON schema variants.
- No full user-management or production service layer.
- No replacement of the current uv single-package setup.

## Acceptance Criteria For This Planning Task

- [x] Current repo state inspected.
- [x] Baseline tests/examples run successfully.
- [x] `prd.md` captures the recommended development path.
- [x] `implement.jsonl` has agent-curated spec context.
- [x] `check.jsonl` has agent-curated spec context.
- [x] User confirms this development path or requests edits.

## Technical Notes

- Baseline commands run on 2026-05-01:
  - `uv run --extra dev pytest`
  - `uv run python scripts/run_examples.py`
- Relevant local docs:
  - `README.md`
  - `docs/development_plan.md`
  - `docs/implementation_research_plan.md`
  - `.trellis/spec/backend/index.md`
- Current task directory:
  - `.trellis/tasks/05-01-trellis-init-development-roadmap/`
