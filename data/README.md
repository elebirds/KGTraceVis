# Data Directory

Large datasets are not tracked by Git.

Place datasets as follows:

- Defect Spectrum / DS-MVTec: `data/external/ds_mvtec/`
- Tennessee Eastman Process: `data/external/tep/`
- Wafer data: `data/external/wafer/`

Tracked data:

- `data/examples/*.json`: tiny evidence examples for tests and demos.
- `data/kg/*.csv`: small curated KG CSV files and source registry.

Ignored data:

- `data/external/`: original datasets.
- `data/interim/`: intermediate processing outputs.
- `data/processed/`: generated reproducible outputs.
