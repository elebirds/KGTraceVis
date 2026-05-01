# Finalize Experiment Scripts V0

## Goal

Finalize the v0 reproducible experiment script surface and paper asset
provenance notes without committing generated run outputs.

## Requirements

- Implement `scripts/run_path_ranking.py` for one evidence file or all examples.
- Script should load validated evidence, run `KGTracePipeline`, print concise
  top-k RCA path summaries, and optionally write JSON under `outputs/`.
- Keep generated run/output files ignored and untracked.
- Update experiment/paper docs to state how generated outputs become stable
  paper assets.
- Preserve the warning that v0 script metrics are reproducibility checks unless
  external ground truth is curated.

## Acceptance Criteria

- [x] `uv run python scripts/run_path_ranking.py` runs on checked-in examples.
- [x] Optional JSON output records command provenance/config fields.
- [x] Docs describe where outputs are generated and how paper assets are copied.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.
- [x] `uv run python scripts/run_noise_experiment.py` passes.
- [x] Generated `outputs/` and `runs/` artifacts are ignored by Git.

## Out Of Scope

- No paper-grade metric claims.
- No LaTeX build.
- No committing generated runs/outputs.
- No external datasets.

## Technical Notes

- Expected files:
  - `scripts/run_path_ranking.py`
  - `docs/experiment_plan.md`
  - `paper/README.md`
  - focused tests if script exposes reusable helpers
