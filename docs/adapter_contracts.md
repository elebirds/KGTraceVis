# Adapter Record Contracts

KGTraceVis ingestion uses two layers:

```text
model-dependent producer -> normalized record -> model-independent Evidence adapter
```

Producer modules are optional and model-aware. They may run detectors or
classifiers, but they must emit normalized records rather than `Evidence`.
Evidence adapters consume records, dataset labels, mask or wafer-map
descriptors, and deterministic statistics. They only emit observed evidence.
They must not emit root causes, ranked paths, or populate `kg_analysis`. For
local real-data producer commands, see
[`docs/dataset_record_producers.md`](dataset_record_producers.md).

## MVTec / DS-MVTec Records

MVTec records use `dataset="mvtec"` and are converted by the MVTec Evidence
adapter.

Required or strongly recommended fields:

- `case_id`
- `object` or `category`
- `defect_type`, `anomaly_type`, or `label`
- `confidence`, `score`, `pred_score`, or `detector_score`

Optional deterministic evidence fields:

- `location`, `morphology`, `severity`
- `mask_stats` or `geometry`
- `bbox`, `centroid`, `area`, `area_ratio`, `eccentricity`, `component_count`
- `image_path`, `mask_path`, `heatmap_path`
- `detector` or `detector_metadata`
- `description` or `caption`

When explicit `location`, `morphology`, or `severity` are absent, the adapter may
derive them from deterministic mask geometry. Detector metadata is provenance
for confidence and raw evidence only; it is not model execution inside the
adapter.

The local producer CLI can populate these fields from fake smoke predictors or
from optional Anomalib exported inferencers selected with `anomalib-torch` or
`anomalib-openvino`. The Anomalib dependency is runtime-only for those producer
backends.

## WM811K Records

WM811K records remain schema-compatible wafer evidence. They use
`dataset="wafer"` and identify WM811K through `adapter="wm811k"` or
`source_dataset="wm811k"`.

Required or strongly recommended fields:

- `case_id` or `wafer_id`
- `failure_pattern`, `pattern`, `label`, or `predicted_pattern`
- `confidence`, `classification_confidence`, or `score`

Optional deterministic evidence fields:

- `zone`, `location`, `morphology`, `defect_density`
- `wafer_map` for tiny checked-in fixtures
- `wafer_map_path` for external arrays
- `map_shape`, `die_count`, `failed_die_count`, `descriptor_stats`
- `saliency_path` or `attention_map_path`
- `annotation_type`

The WM811K adapter emits `Evidence(dataset="wafer")`, sets
`adapter.name="wm811k"`, stores WM811K provenance in
`raw_evidence.extra["wm811k"]`, and stores deterministic descriptors in
`raw_evidence.extra["descriptor_stats"]`. The canonical WM811K pattern is placed
in `anomaly_type` so the current linker and path ranker can use it. A
`spatial_pattern` observation may also be emitted for UI and metric grouping.

Public WM811K records support spatial-pattern evidence analysis, not verified
process root-cause labels. Candidate root causes or plausible explanations are
runtime `KGTracePipeline` outputs only.

The local WM811K producer CLI can populate classifier outputs with
`--model-backend sklearn`, loading trusted local joblib/pickle checkpoints and
recording exposed model classes in classifier metadata.

## Checked-In Fixtures

Tiny record fixtures live under `data/examples/records/`:

- `mvtec_records.jsonl`
- `wm811k_records.jsonl`

These fixtures contain no root-cause answers and do not require model weights,
raw datasets, checkpoints, or producer execution.
