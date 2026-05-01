# Paper Directory

Keep paper text, selected stable figures, tables, and BibTeX references here.

Do not commit LaTeX build files or large generated outputs. Generate figures
under `outputs/`, review them, then copy selected stable assets into
`paper/figures/` with script provenance documented.

## Asset Provenance

Generated experiment outputs belong under ignored paths such as `runs/`,
`outputs/`, or `artifacts/`. Stable paper assets should be small reviewed
derivatives copied into:

- `paper/figures/` for selected figures.
- `paper/tables/` for selected tables or compact JSON-derived summaries.

For each copied asset, document the generating command, input evidence or config,
and source output path in the paper notes or caption source comments. For path
ranking assets, use `uv run python scripts/run_path_ranking.py --write-json`
or the same command with `--evidence <path>`; the generated JSON includes
command, input mode, top-k, pipeline, and CSV KG backend provenance fields.

Do not present v0 noise or path-ranking script outputs as paper-grade metric
claims unless a curated external ground-truth reference set is added and cited.
