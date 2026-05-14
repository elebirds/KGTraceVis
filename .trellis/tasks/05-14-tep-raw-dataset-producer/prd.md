# TEP Raw Dataset Producer

## Goal

Implement a native KGTraceVis TEP raw-data producer that starts from the Kaggle
TEP CSV dataset and emits unified adapter-ready producer records. The logic may
reuse the TEP_KG RBC idea, but must be implemented directly in KGTraceVis rather
than wrapping TEP_KG compatibility artifacts.

Dataset source:

- https://www.kaggle.com/datasets/afrniomelo/tep-csv

Local raw data target:

- `data/raw/tep/`

## Requirements

- Keep raw CSV and archive files out of Git.
- Discover or accept the TEP fault-free and faulty training CSV files.
- Fit a fault-free process profile from raw TEP variables.
- Collect fixed-size faulty windows by fault number and simulation run.
- Compute residual-based channel contributions for each window.
- Emit records compatible with `TepAdapter` and unified RCA provider selection.
- Include both canonical TEP keys and adapter-friendly aliases:
  - `fault_number` and `fault_id`
  - `simulation_run` and `simulation_id`
  - top variables and `variable_contributions`
- Add CLI/workflow support through `scripts/build_dataset_records.py`.
- Add tests with small synthetic TEP CSVs; do not rely on large downloaded files.

## Non-goals

- Do not import or wrap `tep_kg`.
- Do not create a dataset-specific evidence schema.
- Do not commit raw Kaggle data.
- Do not train a deep model for TEP v0.

## Acceptance

- `uv run --extra dev pytest` passes.
- `uv run python scripts/run_examples.py` still passes.
- A user can run a TEP producer command against `data/raw/tep` and obtain JSONL
  records suitable for the existing TEP adapter and RCA path-ranking flow.
