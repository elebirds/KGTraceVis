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
- `mvtec_ad_official_page`: downloaded official MVTec AD dataset page under
  `docs/sources/mvtec_source_bundle/`. Used to support dataset-scope claims:
  industrial inspection benchmark, 15 categories, defect-free training images,
  defect and good test images, and anomaly annotations.
- `mvtec_ad_paper_pdf`: optional MVTec AD paper PDF under the ignored
  `docs/sources/mvtec_source_bundle/raw/` directory when
  `scripts/download_mvtec_sources.py --include-binary` succeeds. Used as local
  provenance for MVTec AD benchmark context and claim-boundary wording.
- `patchcore_arxiv_abs` / `patchcore_arxiv_pdf`: downloaded PatchCore abstract
  page plus optional PDF under `docs/sources/mvtec_source_bundle/`. Used to
  support the model evidence boundary: PatchCore provides anomaly
  detection/localization evidence, not KG root-cause labels.
- `mvtec_object_specific_visual_rule`: deterministic object/label-specific
  candidate mechanism rules. These improve path specificity, but remain
  `review_status=auto` and must be described as candidate investigation targets.
