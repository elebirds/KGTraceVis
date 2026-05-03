# Implementation Route: Adapter-First End-to-End Loop

Date: 2026-05-03

## Target

The next milestone is not a broad paper experiment yet. It is an adapter-first
system milestone:

```text
WM811K / MVTec raw data
-> optional model / algorithm producer
-> model-output record
-> model-independent Evidence adapter
-> validated Evidence JSON
-> KGTracePipeline
-> linked entities, consistency, corrections
-> top_k_paths
-> candidate root cause / plausible explanation with source edges
```

TEP remains a required future scenario, but it should not block this milestone.

## Design Constraints

- Formalize ingestion as two layers:
  1. model-dependent producer,
  2. model-independent Evidence adapter.
- Implement the Evidence adapter layer first. Producers are optional and can be
  added later.
- Keep `dataset="wafer"` for WM811K because the project schema and KG scenario
  rules currently support `mvtec`, `tep`, and `wafer`.
- Add WM811K specificity through `adapter.name`, source refs, raw metadata, and
  wafer scenario KG nodes/edges.
- Do not let adapters write root causes, ranked causes, or `kg_analysis`.
- Do not let model-dependent producer code leak into core Evidence adapter
  logic.
- `KGTracePipeline` remains the only runtime reasoning entry point for scripts,
  Streamlit, and future services.
- For MVTec and public WM811K, root-cause outputs should be titled candidate
  root causes or plausible explanations unless the reference source is verified.
- Manual KG/reference expansion should stay small and source-traceable.

## Current Starting Point

Already available:

- Generic MVTec adapter: `src/kgtracevis/adapters/ds_mvtec_adapter.py`.
- Generic wafer adapter: `src/kgtracevis/adapters/wafer_adapter.py`.
- Batch evidence generation: `src/kgtracevis/adapters/batch.py` and
  `scripts/generate_evidence.py`.
- Runtime pipeline: `src/kgtracevis/core/pipeline.py`.
- Path ranking script: `scripts/run_path_ranking.py`.
- Example evidence files under `data/examples/`.
- Small KG with MVTec and wafer plausible cause paths.
- Tests pass as of this planning task: 84 passed.

Gaps:

- WM811K-specific adapter semantics are not explicit.
- MVTec adapter accepts geometry fields but does not derive morphology/location
  from mask geometry or detector metadata.
- WM811K spatial pattern classes are not represented as a proper evidence/KG
  contract beyond the current tiny `NearfullDefect` example.
- There is no single command that demonstrates:
  `records -> evidence -> pipeline -> top-k paths`.
- Path/root-cause outputs are generated, but not yet packaged as adapter-first
  reproducibility artifacts.

## Phase 1: Adapter Contracts

Goal: define stable input/output contracts before adding more experiments.

### 1.0 Two-Layer Contract

Use this division:

```text
Producer layer:
  raw image / wafer map / model checkpoint / detector runtime
  -> normalized model-output record

Evidence adapter layer:
  normalized model-output record / dataset label / deterministic descriptor
  -> Evidence
```

Producer layer examples:

- MVTec PatchCore/EfficientAD producer emits `pred_score`, `anomaly_map_path`,
  `mask_path`, `bbox`, detector metadata.
- WM811K classifier producer emits `predicted_pattern`, `confidence`,
  `saliency_path`, descriptor stats.

Evidence adapter layer examples:

- `evidence_from_mvtec_record(record)`.
- `evidence_from_wm811k_record(record)` returning `Evidence(dataset="wafer")`.

For this milestone, implement the Evidence adapter layer and deterministic
descriptor helpers. Do not require model checkpoints or training.

### 1.1 WM811K Contract

Keep top-level `dataset="wafer"`.

Add or document a WM811K-specific Evidence adapter entry point, such as:

```text
evidence_from_wm811k_record(record) -> Evidence(dataset="wafer")
```

Candidate input fields:

- `case_id`, `wafer_id`
- `failure_pattern` / `pattern` / `label`
- `classification_confidence` / `score`
- `wafer_map_path`
- `map_shape`, `die_count`, `failed_die_count`
- `defect_density`
- `zone` / derived zone
- `morphology` / derived morphology
- optional `saliency_path`, `attention_map_path`, `descriptor_stats`

Required output observations:

- `object`: wafer
- `anomaly_type`: canonical WM811K pattern name, for compatibility with current
  linker/path-ranker source fields
- `location`: wafer zone or surface/edge/center when derivable
- `morphology`: dense/scattered/ring/line/cluster-style morphology when
  derivable
- `severity`: numeric density/severity when available
- `confidence`: classifier or adapter confidence

Optional output observations:

- `spatial_pattern`: duplicate semantic facet for UI/metrics, while
  `anomaly_type` remains the current pipeline-compatible source field.

Raw/provenance placement:

- `raw_evidence.extra["wm811k"]`: source row metadata and original class label.
- `raw_evidence.extra["descriptor_stats"]`: deterministic wafer-map descriptors.
- `source_ref`: classifier, descriptor rule, or dataset label.
- `metadata["annotation_type"]`: usually `native_ground_truth` for dataset
  pattern labels, `demo_synthetic` for generated logs, or `manual_plausible` for
  explanation references.

### 1.2 MVTec Contract

Strengthen existing MVTec Evidence adapter without making it a root-cause
predictor.

Candidate input fields:

- `case_id`, `object`, `defect_type`
- detector score / anomaly score
- `mask_path`, `heatmap_path`, `bbox`, `area`, `centroid`, `eccentricity`
- DS-MVTec caption or label when available
- optional VLM/caption candidate fields marked low confidence

Required output observations:

- `object`
- `anomaly_type`
- `location`
- `morphology`
- `severity`
- `confidence`

Derivation priority:

1. Strong dataset/manual fields supplied in the record.
2. Mask/geometry deterministic rules.
3. Caption/label parsing.
4. VLM weak candidates only as low-confidence observations.

Raw/provenance placement:

- `raw_evidence.extra["mask_stats"]`
- `raw_evidence.extra["detector"]`
- `raw_evidence.extra["caption_source"]`
- observation-level `source_ref` and `raw_ref`

## Phase 2: KG Support for Top-k Paths

Goal: ensure adapter outputs can link to KG nodes and reach candidate cause
nodes.

### 2.1 WM811K/Wafer KG

Add a small, source-constrained wafer subgraph.

Minimal nodes:

- `WaferObject`
- WM811K pattern/anomaly nodes, e.g. center/local/ring/edge/nearfull/scratch
  pattern nodes as supported by the available records.
- location nodes: wafer surface, center zone, edge zone, ring zone.
- morphology nodes: dense particles, ring pattern, line/scratch pattern,
  clustered pattern, scattered pattern.
- plausible explanation nodes, clearly marked as plausible unless verified.

Minimal edges:

- `WaferObject HAS_ANOMALY <PatternNode>`
- `<PatternNode> HAS_MORPHOLOGY <MorphologyNode>`
- `<PatternNode> OCCURS_ON <LocationNode>`
- `<PatternNode> HAS_PLAUSIBLE_CAUSE <CauseNode>`

Rules:

- Every edge must include source, evidence, confidence, weight, review_status,
  and feedback counters.
- Use `review_status=auto` for plausible mappings unless reviewed.
- Do not claim process RCA for public WM811K.

### 2.2 MVTec KG

Extend only as needed for adapter-first examples.

Add or refine:

- object-to-defect edges for selected MVTec categories,
- defect-to-morphology edges,
- defect-to-location edges,
- defect-to-plausible-cause edges.

Avoid broad manual expansion. Choose a few high-yield cases that demonstrate
the full loop.

## Phase 3: End-to-End Command Path

Goal: create a repeatable command that starts from adapter records, not
hand-authored evidence files.

Recommended implementation:

1. Add record fixtures:
   - `data/examples/records/wm811k_records.jsonl`
   - `data/examples/records/mvtec_records.jsonl`
2. Use `scripts/generate_evidence.py` to write generated evidence under an
   ignored directory such as `outputs/evidence_adapter_v0/`.
3. Extend or add a script that runs the pipeline over generated evidence and
   writes a summary:
   - input record path,
   - generated evidence path,
   - adapter metadata,
   - linked entities,
   - consistency score,
   - correction candidates,
   - top-k paths,
   - candidate root-cause/plausible-explanation target nodes,
   - source edge provenance.

Possible script shape:

```bash
uv run python scripts/run_adapter_pipeline.py \
  --input data/examples/records/wm811k_records.jsonl \
  --dataset wafer \
  --output-dir outputs/adapter_pipeline_v0/wm811k \
  --top-k 5
```

Keep `scripts/generate_evidence.py` as a simple evidence writer. The new script
can orchestrate generation plus analysis, but reusable logic should live under
`src/kgtracevis/`.

## Phase 4: Tests

Goal: make the adapter-first loop hard to accidentally break.

### Unit Tests

MVTec:

- input record with detector/mask/caption fields produces valid Evidence.
- adapter does not populate `kg_analysis`.
- observations have stable IDs and provenance.
- geometry-derived fields are used when explicit fields are absent.

WM811K:

- WM811K record produces `Evidence(dataset="wafer")`.
- `adapter.name` or metadata identifies WM811K.
- pattern maps to `anomaly_type` and optional `spatial_pattern`.
- location/morphology/severity/confidence observations are produced.
- synthetic/demo log fields are marked as demo-only when present.

### Integration Tests

- Generated MVTec evidence runs through `KGTracePipeline` and returns top-k
  paths with source edges.
- Generated WM811K evidence runs through `KGTracePipeline` and returns top-k
  paths with source edges.
- The orchestrating script writes a JSON summary with candidate target nodes.

### QA Tests

- KG CSV loader passes for new nodes/edges.
- KG QA has no issues; warnings are understood and documented.
- Reference rows do not claim verified RCA unless eligible.

## Phase 5: Paper-Ready Experiment Layer

Goal: after adapter-first execution works, produce defensible tables.

Metrics to group by dataset and source:

- schema validity rate,
- entity linking top-1/top-k,
- consistency precision/recall under injected noise,
- correction top-1/top-k,
- noise recovery rate,
- path hit only against explicitly scoped plausible/reference rows.

Recommended table scopes:

- `adapter_evidence_quality`: schema/linking/provenance completeness.
- `noise_correction`: clean vs noisy evidence.
- `plausible_explanation`: top-k candidate path hit against scoped references.

Do not make verified RCA accuracy the main table for MVTec/WM811K unless the
references are upgraded.

## Phase 6: Deferred TEP Track

TEP remains required, but starts after WM811K/MVTec adapter-first loop is
stable.

TEP route:

1. Define TEP adapter input record contract.
2. Generate variable/fault evidence without writing root cause into adapter
   output.
3. Expand TEP KG variable-unit-fault-cause edges.
4. Run the same adapter-to-pipeline script.
5. Add TEP path-ranking metrics when reference mapping is defensible.

## Suggested Implementation PR Slices

### PR1: Two-Layer Contracts and Fixtures

- Document producer-output record contracts.
- Add WM811K Evidence adapter entry point or documented wrapper.
- Add small WM811K and MVTec producer-output record fixtures.
- Add tests for Evidence adapter output shape and provenance.

### PR2: KG Support

- Add minimal wafer/WM811K KG nodes and edges.
- Add only the MVTec edges needed for selected examples.
- Run KG QA and update tests.

### PR3: Adapter-to-Pipeline Script

- Add reusable orchestration helper under `src/kgtracevis/`.
- Add CLI script for record -> evidence -> analysis summary.
- Add integration tests.

### PR4: Experiment Tables

- Add grouped summary generation.
- Add metric-scope labels.
- Write generated outputs under `runs/` or `outputs/`.

### PR5: Demo/Docs Polish

- Update README/docs with the new command.
- Keep Streamlit changes minimal: show generated evidence, top-k paths, source
  edges, and candidate explanation target.

### PR6: Optional Producers

- Add model-dependent producers only after adapter-first loop is stable.
- Keep producers behind optional dependencies/configuration.
- Producer output must conform to the same record contract already consumed by
  Evidence adapters.

## Implementation Progress

2026-05-04:

- Implemented model-independent MVTec and WM811K Evidence adapters with small
  producer-output-style fixtures.
- Added deterministic mask/wafer descriptor helpers and adapter contract docs.
- Added `scripts/run_adapter_pipeline.py` for
  `records -> Evidence -> KGTracePipeline -> top-k paths -> scoped table`.
- Integrated MVTec and WM811K adapter pipeline stages into
  `scripts/run_experiment_suite.py`, including JSON and CSV output provenance.
- Verified the default v0 suite now runs 8 commands, including both adapter
  pipeline stages.
- Added `docs/paper_experiment_protocol.md` to define the paper-facing
  experiment protocol, reference eligibility rules, dataset-specific boundaries,
  and command/artifact eligibility for the adapter-first MVTec/WM811K milestone.
- Added `scripts/build_paper_tables.py` and reusable paper-table manifest
  builders to group generated outputs by dataset, noise type, annotation type,
  and metric scope while preserving command provenance.

## Quality Gate

Before closing the milestone:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/run_examples.py
uv run python scripts/run_experiment_suite.py
uv run python scripts/run_adapter_pipeline.py --input <wm811k-records> --dataset wafer --output-dir <ignored-output>
uv run python scripts/run_adapter_pipeline.py --input <mvtec-records> --dataset mvtec --output-dir <ignored-output>
```

If KG CSVs change:

```bash
uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json
uv run python scripts/import_kg.py --dry-run
```

## Key Risks

- Adding `wm811k` as a new dataset literal would ripple through schema, KG
  scenario rules, tests, and docs. Prefer `dataset="wafer"` with WM811K adapter
  metadata.
- If WM811K pattern is only stored as a non-linkable `spatial_pattern`, the
  current path ranker may not start from it. Keep the canonical pattern in
  `anomaly_type`, or intentionally extend linker/path-ranker facets.
- Public WM811K does not justify verified process RCA claims. Keep explanation
  references scoped.
- Over-expanding KG manually before adapter execution works will create busywork
  without proving the system loop.
- Collapsing producer and Evidence adapter into one module will make Option C
  block Option B. Keep them separated.
