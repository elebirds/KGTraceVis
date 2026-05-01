# Build Experiment Automation And KG QA

## Goal

Add AI-owned coding infrastructure that automates v0 experiment orchestration
and KG quality assurance without requiring new human industrial judgments or
inventing ground truth.

This task should make the existing scripts easier to run together and produce
machine-readable summaries for later paper tables.

## What I Already Know

- `scripts/run_examples.py`, `scripts/run_noise_experiment.py`,
  `scripts/run_path_ranking.py`, `scripts/build_kg.py`, and
  `scripts/import_kg.py --dry-run` are all runnable.
- Current generated outputs under `runs/` and `outputs/` are ignored by Git.
- Existing KG validation checks required CSV columns, provenance fields,
  confidence/weight contracts, review status, and feedback counters.
- The next AI-owned work should not create or claim external RCA ground truth.
- The useful missing pieces are:
  - a single script to run the v0 script suite and collect outputs,
  - a KG QA report with warnings/check categories,
  - table-friendly JSON/CSV summaries for later paper use.

## Requirements

### Experiment Automation

- Add a script or reusable module that runs the v0 local experiment suite:
  - examples validation,
  - KG build/validation summary,
  - Neo4j dry-run summary,
  - noise experiment summary,
  - path ranking summary.
- Save one consolidated JSON summary under ignored `runs/<experiment_name>/`
  or `outputs/`.
- Include provenance:
  - command name,
  - timestamp,
  - config paths,
  - input directory,
  - git commit if available,
  - metric scope note.
- Keep script output concise.
- Do not commit generated run/output files.

### KG QA

- Add reusable KG QA helpers that inspect the loaded KG and produce a structured
  report.
- Check at least:
  - missing or invalid provenance fields,
  - confidence/weight contract violations,
  - invalid review status,
  - negative feedback counters,
  - isolated nodes,
  - edges whose head/tail nodes are missing when checking raw CSV rows,
  - duplicate edge IDs in raw CSV rows,
  - reviewed edges with low confidence warning.
- Provide a CLI entry, preferably `scripts/run_kg_qa.py`, that prints a concise
  summary and optionally writes JSON under ignored outputs.
- QA must report warnings/issues; it must not auto-invent or edit KG facts.

### Table-Friendly Summaries

- Provide a compact table-oriented output from experiment automation or a helper
  that can later be copied into `paper/tables/` after human review.
- Mark all values as v0 reproducibility outputs, not paper-grade ground truth.

## Acceptance Criteria

- [x] Experiment automation script runs all v0 checks locally.
- [x] Consolidated JSON summary includes provenance and metric scope note.
- [x] KG QA script runs on checked-in KG CSV files.
- [x] KG QA report is structured and test-covered.
- [x] Generated outputs are ignored by Git.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.
- [x] `uv run python scripts/run_noise_experiment.py` passes.
- [x] `uv run python scripts/run_path_ranking.py` passes.
- [x] New automation/QA scripts pass.

## Out Of Scope

- No new KG facts.
- No external dataset ingestion.
- No paper-grade ground-truth claims.
- No LaTeX build.
- No generated outputs committed.
- No web or cloud orchestration.

## Technical Notes

- Likely implementation files:
  - `src/kgtracevis/experiments/` or similar reusable experiment helpers,
  - `src/kgtracevis/kg/qa.py` or `src/kgtracevis/kg_construction/qa.py`,
  - `scripts/run_experiment_suite.py`,
  - `scripts/run_kg_qa.py`,
  - tests under `tests/`.
- Reuse existing script logic where practical, but keep reusable checks under
  `src/kgtracevis/`.
