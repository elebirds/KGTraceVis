# Experiment Plan

The v0 reproducible path is:

```text
example JSON -> KG link -> consistency score -> correction -> path ranking -> demo
```

Formal experiments should run through scripts, save their configs, and write
outputs under `runs/` or `outputs/`.

## V0 Scripts

- `uv run python scripts/run_examples.py` validates the checked-in examples and
  runs the full `KGTracePipeline`.
- `uv run python scripts/run_noise_experiment.py` writes deterministic noise
  reproducibility summaries under `runs/<experiment_name>/`.
- `uv run python scripts/run_path_ranking.py` prints concise top-k path ranking
  summaries for all checked-in examples.
- `uv run python scripts/run_path_ranking.py --evidence <path> --write-json`
  analyzes one evidence file and writes a provenance-rich JSON summary under
  `outputs/path_ranking_v0/`.

Generated `runs/`, `outputs/`, and `artifacts/` content is ignored by Git. Do
not commit these raw generated outputs. If a generated table, figure, or JSON
snippet is selected for the paper, review it, copy only the stable derived asset
into `paper/figures/` or `paper/tables/`, and record the source command plus
input path in the paper asset notes.

## Metric Scope

The v0 script metrics are reproducibility checks over checked-in examples or
clean-run references. They are not paper-grade ground-truth claims unless an
external ground-truth reference set is curated, documented, and wired into the
experiment configuration.
