# Implementation Research Plan

Status: development reference.

This plan converts the research brief into concrete engineering work. It should
guide development until formal experiment design replaces it.

## Near-Term Development Order

1. Keep the in-memory KG path as the default backend.
2. Expand the checked-in KG with curated MVTec RCA reference edges.
3. Add scenario-specific CSV merge support.
4. Add noisy evidence generation.
5. Add metrics for linking, correction, and RCA ranking.
6. Build a Streamlit page that exposes the current pipeline outputs.

## Data Files To Add

Suggested files:

```text
data/kg/mvtec_rca_reference.csv
data/kg/tep_reference_edges.csv
data/kg/wafer_reference_edges.csv
docs/mvtec_rca_annotation_guide.md
```

For v0, `mvtec_rca_reference.csv` can use the same edge schema as
`data/kg/edges.csv`:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

This lets the loader merge global and scenario-specific files without adding
another parser.

## Code Tasks

### KG Loader

Current status: `KnowledgeGraph.from_csv()` loads one node CSV and one edge CSV.

Next:

- Add `from_paths(nodes_paths, edges_paths)`.
- Deduplicate nodes by ID.
- Deduplicate edges by `(head, relation, tail, scenario)`.
- Refuse to overwrite `review_status=reviewed` edges unless explicitly allowed.

### MVTec Adapter

Current status: placeholder.

Next:

- Read object, defect type, optional caption, and mask path.
- Derive morphology from mask geometry when mask is available.
- Derive location from mask centroid or bounding box region.
- Store dataset-specific details in `raw_evidence.extra`.

Minimum output fields:

```text
object
anomaly_type
location
morphology
severity
raw_evidence.image_region
raw_evidence.heatmap_path
raw_evidence.description
```

### Noise Injection

Current status: placeholder.

Next:

- Implement deterministic field corruption with a fixed seed.
- Support anomaly type replacement.
- Support location replacement.
- Support morphology replacement.
- Support variable deletion.
- Support log event deletion.
- Record `is_noisy`, `noise_level`, `corrupted_fields`, and
  `clean_reference`.

### Metrics

Current status: placeholders.

Next:

- `schema_validity_rate`.
- `top_k_linking_accuracy`.
- `inconsistency_detection_precision_recall`.
- `correction_accuracy`.
- `top_k_correction_accuracy`.
- `top_k_root_cause_accuracy`.
- `mrr`.
- `path_hit_rate`.

### Streamlit Demo

Current status: placeholder.

Next:

- Case selector from `data/examples` and later `runs`.
- Evidence JSON viewer.
- Linked entity table.
- Consistency score and inconsistent fields.
- Correction candidate table.
- RCA path list with source edges.
- Basic what-if editor for evidence fields.

## Development Experiments

### Experiment A: MVTec Clean RCA

Input:

- curated MVTec evidence examples,
- manual RCA reference edges.

Output:

- top-1 RCA accuracy,
- top-3 RCA accuracy,
- MRR,
- path hit rate.

### Experiment B: MVTec Noisy RCA

Input:

- same examples as Experiment A,
- corrupted anomaly type / location / morphology fields.

Output:

- inconsistency precision / recall,
- correction accuracy,
- RCA recovery rate.

### Experiment C: TEP RCA

Input:

- variable and fault evidence examples,
- variable-unit-fault-root cause KG edges.

Output:

- top-k RCA accuracy,
- MRR,
- path hit rate.

### Experiment D: Wafer Case Study

Input:

- one or more image-log evidence examples,
- source-constrained wafer process KG.

Output:

- case study narrative,
- path plausibility,
- expert acceptance if available.

## Formal Experiment Gate

Before treating results as paper experiments, check:

- every RCA reference edge has an explicit source and evidence text,
- reviewed edges were actually reviewed,
- MVTec claims say "curated plausible RCA reference", not "true factory root
  cause",
- TEP metrics use a defensible fault-label mapping,
- generated run configs and metrics are saved under `runs/`,
- selected figures/tables document their generation scripts.
