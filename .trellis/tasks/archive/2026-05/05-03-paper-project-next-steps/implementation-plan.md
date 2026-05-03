# Implementation Plan: Two-Layer Adapter Milestone

Date: 2026-05-04

## Milestone Goal

Implement the model-independent Evidence adapter layer for MVTec/DS-MVTec and
WM811K, prove it runs through the existing KGTracePipeline, and leave a clean
contract for future model-dependent producers.

Pipeline target:

```text
producer-output record
-> Evidence adapter
-> Evidence JSON with empty kg_analysis
-> KGTracePipeline.analyze(...)
-> linked_entities / consistency / corrections / top_k_paths
-> candidate root cause or plausible explanation target
```

## Architecture

Use two explicit layers:

1. **Producer layer**
   - Model-dependent and optional.
   - Future modules may run PatchCore/EfficientAD for MVTec or CNN/ViT for
     WM811K.
   - Output is a normalized record.
   - Not implemented in the first milestone.
2. **Evidence adapter layer**
   - Model-independent and required now.
   - Consumes normalized producer records, labels, mask stats, wafer maps, and
     deterministic descriptors.
   - Produces Pydantic `Evidence`.
   - Must never populate `kg_analysis` or root-cause fields.

## Implementation Order

### Step 1: Producer-Output Record Contracts

Files:

- `docs/adapter_contracts.md` or `docs/adapter_evidence_generation_plan_cn.md`
- `data/examples/records/mvtec_records.jsonl`
- `data/examples/records/wm811k_records.jsonl`

Tasks:

- Document the producer-output record shape for MVTec.
- Document the producer-output record shape for WM811K.
- Add tiny checked-in fixtures, not raw datasets:
  - MVTec clean scratch-like case.
  - MVTec noisy morphology/location case.
  - WM811K clean nearfull/edge/ring-like case.
  - WM811K noisy morphology/location case.

Acceptance:

- Fixtures contain no root-cause answer.
- Fixtures contain enough fields to generate required observations.
- Fixtures are small and safe to commit.

### Step 2: Deterministic Feature Helpers

Files:

- `src/kgtracevis/mask/mask_feature_extractor.py`
- likely new `src/kgtracevis/mask/wafer_map_features.py`
- tests under `tests/`

Tasks:

- Implement lightweight mask/stat helpers:
  - normalize supplied bbox/centroid/area/eccentricity stats,
  - optionally compute stats from simple arrays later,
  - derive severity from area ratio,
  - derive morphology from eccentricity/component style,
  - derive location from centroid/zone.
- Implement lightweight wafer map descriptor helpers:
  - accept simple nested lists or precomputed descriptor stats,
  - compute/normalize failed die ratio,
  - derive zone/location: center, edge, ring, local, surface,
  - derive morphology: dense, ring, clustered, scattered, linear/scratch.

Acceptance:

- Helpers are deterministic.
- Helpers do not import heavy ML packages.
- Tests cover explicit stats and minimal array/list inputs.

### Step 3: MVTec Evidence Adapter

Files:

- `src/kgtracevis/adapters/ds_mvtec_adapter.py`
- `tests/test_adapters.py` or new adapter test module

Tasks:

- Preserve existing record-field behavior.
- Add deterministic fallback when explicit location/morphology/severity are
  absent:
  - use `mask_stats`,
  - use bbox/centroid/area/eccentricity,
  - use detector score as confidence/severity when appropriate.
- Add provenance metadata:
  - `raw_evidence.extra["mask_stats"]`
  - `raw_evidence.extra["detector"]`
  - observation `source_ref` such as `adapter:mvtec`, `mask_geometry`,
    `detector_output`, or `dataset_label`.
- Keep `kg_analysis` empty.

Acceptance:

- Existing adapter tests still pass.
- New MVTec fixture converts to Evidence.
- Result has stable observations for object/anomaly_type/location/morphology/
  severity/confidence.
- No root-cause field appears in adapter output.

### Step 4: WM811K Evidence Adapter

Files:

- likely new `src/kgtracevis/adapters/wm811k_adapter.py`
- `src/kgtracevis/adapters/__init__.py`
- `src/kgtracevis/adapters/batch.py`
- tests under `tests/`

Design:

- Return `Evidence(dataset="wafer")`.
- Set `adapter.name="wm811k"` or metadata identifying WM811K.
- Keep top-level `anomaly_type` as canonical WM811K pattern so existing linker
  and path ranker can use it.
- Optionally add `spatial_pattern` observation for UI/metrics, but do not rely
  on it for path ranking unless linker/path-ranker is extended.

Tasks:

- Add `evidence_from_wm811k_record(record)`.
- Support record fields:
  - `failure_pattern`, `pattern`, `label`, `predicted_pattern`,
  - `confidence`, `classification_confidence`, `score`,
  - `wafer_map`, `wafer_map_path`,
  - `defect_density`, `failed_die_count`, `die_count`,
  - `zone`, `morphology`, `descriptor_stats`,
  - optional `saliency_path`, `attention_map_path`.
- Produce observations:
  - object,
  - anomaly_type,
  - spatial_pattern optional,
  - location,
  - morphology,
  - severity,
  - confidence.
- Store WM811K provenance in `raw_evidence.extra["wm811k"]` and
  `raw_evidence.extra["descriptor_stats"]`.

Acceptance:

- WM811K record produces schema-valid `Evidence(dataset="wafer")`.
- Adapter metadata identifies WM811K.
- `kg_analysis` remains empty.
- No root cause is produced by adapter.

### Step 5: KG Minimal Support

Files:

- `data/kg/nodes.csv`
- `data/kg/edges.csv` or scenario-specific wafer edge file if existing loader
  supports it
- `data/references/wafer_plausible_reference.csv`
- tests for KG QA/reference boundaries

Tasks:

- Add only nodes/edges needed for first WM811K fixtures.
- Add aliases matching canonical WM811K labels:
  - nearfull / Near-full,
  - center,
  - edge-ring,
  - edge-loc,
  - scratch,
  - random/local as needed by fixtures.
- Add plausible explanation nodes conservatively.
- Add `HAS_MORPHOLOGY`, `OCCURS_ON`, and `HAS_PLAUSIBLE_CAUSE` edges.

Acceptance:

- `uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json`
  reports no issues.
- New edges include source/evidence/confidence/weight/review_status/counters.
- WM811K fixture can reach at least one candidate target in top-k paths.

### Step 6: Adapter-to-Pipeline Orchestration

Files:

- likely new `src/kgtracevis/experiments/adapter_pipeline.py`
- new `scripts/run_adapter_pipeline.py`
- tests for script/helper behavior

Tasks:

- Load records using existing batch loader.
- Convert records to Evidence using selected adapter.
- Optionally write generated Evidence JSON under ignored output directory.
- Run `KGTracePipeline.analyze(...)`.
- Write JSON summary with:
  - input record path,
  - generated evidence payload or path,
  - adapter name,
  - linked entity count,
  - consistency score,
  - correction candidates,
  - top-k paths,
  - target candidate root-cause/plausible explanation nodes,
  - source edge provenance.

Acceptance:

- Command works for MVTec fixture records.
- Command works for WM811K fixture records.
- Output explicitly says candidate/plausible explanation, not verified RCA.

### Step 7: Verification and Documentation

Files:

- `README.md`
- `docs/adapter_evidence_generation_plan_cn.md`
- `docs/experiment_plan.md`
- tests as needed

Tasks:

- Document the two-layer ingestion architecture.
- Document the adapter-to-pipeline command.
- Document dataset boundaries:
  - MVTec: no verified factory RCA.
  - WM811K: pattern/evidence analysis, not verified process RCA.
  - TEP: future supported scenario.

Acceptance:

- Docs match implemented commands.
- User can run the adapter-first demo from record fixtures.

## First Implementation Batch

Recommended first batch for the implement agent:

1. Add WM811K adapter entry point.
2. Add deterministic descriptor helpers for precomputed stats and tiny arrays.
3. Add MVTec deterministic fallback using precomputed mask stats.
4. Add record fixtures.
5. Add adapter unit tests.

This batch should avoid KG CSV changes if possible by choosing fixture labels
that already link:

- MVTec: `scratch`, `surface`, `linear`.
- WM811K/wafer: `nearfull`, `wafer_surface`, `dense_particles`.

After that passes, the next batch can expand KG to more WM811K classes.

## Agent Prompt for First Batch

Use with `trellis-implement`:

```text
Implement the first adapter-first batch from
.trellis/tasks/05-03-paper-project-next-steps/implementation-plan.md:

- add model-independent WM811K Evidence adapter support while keeping
  dataset="wafer";
- add deterministic feature helpers for precomputed mask/wafer-map stats;
- strengthen MVTec adapter fallback from mask_stats/geometry;
- add tiny record fixtures for MVTec and WM811K;
- add unit tests proving adapters emit schema-valid Evidence, stable
  observations, provenance, empty kg_analysis, and no root-cause fields.

Do not implement model-dependent producers yet. Do not train or download models.
Avoid broad KG expansion in this first batch unless required for tests.
```

## Quality Commands

Minimum after first batch:

```bash
uv run --extra dev pytest tests/test_adapters.py
uv run --extra dev pytest
uv run python scripts/run_examples.py
```

After adapter-to-pipeline script lands:

```bash
uv run python scripts/run_adapter_pipeline.py --input data/examples/records/wm811k_records.jsonl --dataset wafer --output-dir outputs/adapter_pipeline_v0/wm811k
uv run python scripts/run_adapter_pipeline.py --input data/examples/records/mvtec_records.jsonl --dataset mvtec --output-dir outputs/adapter_pipeline_v0/mvtec
```

