# MVTec / Defect Spectrum Sources

Record source excerpts or links used for KG construction here. Do not commit
large copyrighted PDFs or raw datasets.

## Coverage-First Candidate KG Sources

- `mvtec_calibrated_source_label`: local calibrated MVTec producer records under
  `runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl`. Used for
  object and defect-label coverage. These labels are observed/source labels, not
  verified factory root causes.
- `mvtec_mask_geometry`: local adapter/KGTrace table under
  `runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_table.csv`.
  Used for deterministic morphology/location constraints derived from masks and
  adapters.
- `mvtec_plausible_visual_mechanism`: low-confidence curated visual mechanism
  rules used only for candidate explanation paths. These edges must remain
  reviewable and should not be described as MVTec ground-truth RCA.
