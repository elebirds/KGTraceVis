# Evidence Schema

All dataset adapters must output the unified anomaly evidence JSON schema.

Required top-level fields:

- `case_id`
- `dataset`
- `source`
- `object`
- `anomaly_type`
- `location`
- `morphology`
- `severity`
- `confidence`
- `timestamp`
- `raw_evidence`
- `normalized_evidence`
- `kg_analysis`

Canonical adapter fields:

- `observations`
- `adapter`

Optional feedback-compatible field:

- `human_feedback`

`observations` is the only canonical list of stable observed evidence items for
KG reasoning. New dataset adapters and checked-in examples must populate
observations for observed reasoning facets such as `object`, `anomaly_type`,
`location`, `morphology`, `variable`, and `log_event`.

Top-level fields describe the evidence envelope and display metadata; they are
not the KG reasoning contract. `raw_evidence` stores source-specific provenance
and raw model or dataset details. Strict validation is available through
`load_evidence_json(..., require_canonical_observations=True)`.

For MVTec-style image uploads, `anomaly_type` must distinguish model output from
semantic prior. Anomalib-style detectors provide anomaly score, heatmap, mask,
and geometry; they do not by themselves infer defect names such as `crack` or
`scratch`. If no reviewed native/operator label is available, set the
observation name to `unknown` or `visual_anomaly` and carry detector outputs in
`raw_evidence.extra` plus geometry observations. If a human or dataset folder
provides a defect name, record its source as native label or human prior
provenance instead of treating it as detector output.

Each observation item must include:

- `obs_id`
- `facet`
- `name`

Each observation may also include `display_name`, `value`, `value_type`,
`unit`, `direction`, `confidence`, `source_ref`, `raw_ref`, `time_window`, and
`metadata`.

When `adapter` is present, `adapter.produces_root_cause` must be `false` for
dataset adapters. Adapters produce observed anomaly evidence only;
`kg_analysis` is empty at ingestion time and is populated by `KGTracePipeline`
at runtime.
