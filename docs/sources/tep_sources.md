# TEP Sources

Record source excerpts, table references, or links used for TEP KG construction here.

## Local Project Artifacts Used for the Curated Seed KG

The first checked-in TEP seed layer is intentionally small and reviewable. It
uses local sibling-project artifacts as provenance, not as automatic ground
truth.

- `tep_kg_variable_mapping`
  - Local path: `/Users/hhm/code/TEP_KG/data/processed/kg/tep_variable_mapping.jsonl`
  - Use: XMEAS/XMV channel aliases and canonical TEP variable nodes.
  - Boundary: channel mapping only; it does not provide root-cause labels.

- `tep_kg_fault_labels_v3`
  - Local path: `/Users/hhm/code/TEP_KG/data/processed/rca/fault_root_cause_labels.json`
  - Use: TEP IDV(1-19) fault anchors and semantic proxy lists.
  - Boundary: KGTraceVis stores derived variable-support edges as
    `review_status=auto`; they are candidate RCA support, not online causal
    proof.

- `rootlens_tep_runtime_projection`
  - Local path: `/Users/hhm/code/RootLens/scripts/build-runtime.py`
  - Use: cross-check that RootLens route2 runtime expects TEP fault anchors,
    variable contribution evidence, and examples such as Fault 06 with
    `XMEAS_1` / `XMV_3`.
  - Boundary: visualization/runtime alignment only; no direct KG mutation.

- `kgtracevis_tep_producer_contract`
  - Local path: `docs/dataset_record_producers.md`
  - Use: documents that the KGTraceVis TEP producer emits residual contribution
    records and `morphology="multivariate_residual_shift"`.
  - Boundary: evidence-production contract, not an external industrial fact.
