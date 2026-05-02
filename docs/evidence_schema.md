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

`observations` is the canonical list of stable evidence items for KG reasoning.
New dataset adapters and checked-in examples must populate observations for
observed reasoning facets such as `object`, `anomaly_type`, `location`,
`morphology`, `variable`, and `log_event`.

The legacy top-level fields and `raw_evidence.variables` / `raw_evidence.log_events`
remain runtime-compatible for demo safety and older payloads, but they are
compatibility-only. When an observation and a legacy field disagree, linkers and
downstream KG reasoning should use the observation. Strict validation is
available through `load_evidence_json(..., require_canonical_observations=True)`.

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
