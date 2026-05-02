# Reference Files

This directory stores small reference labels for evaluation and demo boundary
documentation. Reference rows are not adapter input and must not be copied into
`Evidence.kg_analysis`.

The current files are v0-scale examples:

- `mvtec_plausible_rca_reference.csv`: curated plausible visual explanation
  references for MVTec-style demo cases. These are not verified factory root
  causes.
- `tep_rca_reference.csv`: process-fault style reference rows for the TEP demo
  case. TEP is the preferred direction for quantitative RCA/path-ranking work.
- `wafer_plausible_reference.csv`: wafer traceability demo references. These
  are not public verified process RCA labels.

Use `evaluation_eligible` and `annotation_type` to decide whether a row can
support a paper metric. LLM-only or manual demo rows should stay out of primary
ground-truth claims until reviewed.
