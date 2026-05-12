# Coverage-First KG Hardening Pipeline

This pipeline builds paper-review candidate KG artifacts for MVTec and WM811K.
It is coverage-first: the KG should cover relevant evidence fields, common
defect classes, and typical reasoning errors even when some candidate mechanism
edges remain low-confidence.

## Claim Boundary

MVTec paths are curated plausible explanations, not verified factory root
causes. WM811K model outputs are defect-pattern evidence, not process RCA
labels. Candidate mechanism paths are investigation aids and must remain
source-attached, confidence-scored, and reviewable.

## Steps

1. Run case explainability audit:

   ```bash
   uv run python scripts/audit_case_explainability.py
   ```

   Outputs:
   - `runs/paper_case_kg_audit/mvtec_case_ranking.csv`
   - `runs/paper_case_kg_audit/mvtec_case_ranking.json`
   - `runs/paper_case_kg_audit/top_cases.md`
   - `runs/paper_case_kg_audit/wm811k_case_ranking.csv`

2. Build candidate KG and before/after reasoning artifacts:

   ```bash
   uv run python scripts/build_case_kg.py --overwrite
   ```

   Outputs:
   - `runs/paper_case_kg/nodes_candidate.csv`
   - `runs/paper_case_kg/edges_candidate.csv`
   - `runs/paper_case_kg/kg_generation_summary.json`
   - `runs/paper_case_kg/validation_report.json`
   - `runs/paper_case_kg/edge_review_queue.csv`
   - `runs/paper_case_kg/coverage_report.json`
   - `runs/paper_case_kg/selected_case_reasoning_before_after.csv`
   - `runs/paper_case_kg/top_case_explanations.md`

3. Optionally rerun an adapter pipeline with candidate KG overlay:

   ```bash
   uv run python scripts/run_adapter_pipeline.py \
     --input runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl \
     --dataset mvtec \
     --output-dir runs/paper_case_kg/manual_overlay_check \
     --kg-node-path runs/paper_case_kg/nodes_candidate.csv \
     --kg-edge-path runs/paper_case_kg/edges_candidate.csv \
     --overwrite
   ```

## KG Layers

- `observed_evidence`: objects, defect types, WM811K patterns, morphology, and
  locations from dataset labels, model outputs, masks, or wafer-map descriptors.
- `semantic_constraint`: `HAS_MORPHOLOGY`, `OCCURS_ON`, `HAS_LOCATION`, and
  `HAS_ANOMALY` edges that support entity linking and consistency checking.
- `candidate_mechanism`: `HAS_PLAUSIBLE_CAUSE` and `PART_OF` edges that support
  candidate path ranking. These are weak explanations unless reviewed.

## Confidence Rules

- Dataset labels, model outputs, mask statistics, and wafer-map descriptors are
  high-confidence observed evidence, not RCA.
- Defect-to-morphology/location constraints are medium to high confidence.
- Generic visual and wafer-process mechanism candidates are low to medium
  confidence and default to `review_status=auto`.
- Reviewed edges may raise confidence, but paper wording still uses
  candidate/plausible explanation unless an external RCA reference exists.

## Promotion Rule

Generated rows stay under `runs/` by default. Only manually reviewed, stable
candidate rows should be copied into tracked `data/kg/*.csv`.

Use `edge_review_queue.csv` to triage candidate edges:

- high priority: low-confidence candidate mechanism edges that should be
  reviewed before being emphasized in the paper;
- medium priority: candidate mechanism or borderline semantic-constraint rows
  that need spot checks;
- low priority: observed evidence and straightforward semantic rows that can be
  bulk-approved once their source registry entries are accepted.
