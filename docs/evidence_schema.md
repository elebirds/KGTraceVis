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

Optional feedback-compatible field:

- `human_feedback`
