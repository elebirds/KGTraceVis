# Adapter Options: MVTec/DS-MVTec and WM811K

Date: 2026-05-03

## Purpose

Research and decision options for implementing the first adapter-focused
milestone:

```text
dataset record / detector output
-> adapter
-> Evidence JSON
-> KGTracePipeline
-> top_k_paths
-> candidate root cause / plausible explanation
```

## Sources Checked

External:

- MVTec AD official dataset page:
  `https://www.mvtec.com/research-teaching/datasets/mvtec-ad`
- MVTec AD paper PDF:
  `https://www.mvtec.com/fileadmin/Redaktion/mvtec.com/company/research/datasets/mvtec_ad.pdf`
- Defect Spectrum Hugging Face dataset page:
  `https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum`
- Scientific Reports WM811K paper:
  `https://www.nature.com/articles/s41598-023-34147-2`
- Journal of Intelligent Manufacturing WM811K paper:
  `https://link.springer.com/article/10.1007/s10845-024-02377-4`
- Anomalib getting started / prediction examples:
  `https://anomalib.readthedocs.io/en/latest/markdown/get_started/anomalib.html`
- Anomalib PatchCore docs:
  `https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html`

Local:

- `src/kgtracevis/adapters/ds_mvtec_adapter.py`
- `src/kgtracevis/adapters/wafer_adapter.py`
- `src/kgtracevis/adapters/batch.py`
- `src/kgtracevis/core/pipeline.py`
- `src/kgtracevis/kg/path_ranker.py`
- `data/kg/nodes.csv`
- `data/kg/edges.csv`
- `data/kg/mvtec_rca_reference.csv`
- `tests/test_adapters.py`
- `pyproject.toml`

## Research Facts

### MVTec / DS-MVTec

- MVTec AD is a benchmark for industrial visual anomaly detection.
- It contains 15 object/texture categories, defect-free training images, test
  images with defects, and pixel-precise anomaly annotations.
- The MVTec AD paper frames the task as unsupervised anomaly detection and
  localization, not verified factory root-cause diagnosis.
- Defect Spectrum extends MVTec-style data with richer semantics, masks,
  rgb masks, and descriptive captions.
- Anomalib PatchCore/EfficientAD-style inference can provide image-level score
  and pixel-level anomaly map outputs. These are suitable adapter inputs.

Adapter implication:

- MVTec adapter should convert detector/record outputs into observed evidence:
  object, defect/anomaly type, morphology, location, severity, confidence,
  heatmap/mask/caption provenance.
- It should not produce root cause directly.

### WM811K

- WM811K is widely used for wafer map failure pattern classification.
- Literature reports 811,457 wafer maps, with 172,950 labeled wafers and a
  relatively small/imbalanced subset of patterned defect classes.
- Common classes include Center, Donut, Edge-Loc, Edge-Ring, Loc, Random,
  Scratch, Near-full, and None.
- Wafer maps have varying sizes/resolutions, so preprocessing/resizing and
  class imbalance are major concerns.
- Public WM811K is much stronger for spatial pattern recognition than verified
  process-root-cause analysis.

Adapter implication:

- WM811K adapter should emit wafer-map spatial evidence:
  pattern/anomaly type, zone/location, morphology, severity/density,
  classifier confidence, raw map metadata.
- It should use `dataset="wafer"` in current schema, with `adapter.name` or
  metadata identifying WM811K.
- Candidate cause/path outputs should remain plausible explanations unless
  stronger references become available.

## Updated Architecture Decision

User proposed a better formal split:

```text
model / algorithm producer
-> model-output record
-> evidence adapter
-> Evidence JSON
-> KGTracePipeline
```

This should replace the earlier idea that "adapter" might include everything.
The project should use two explicit layers:

1. **Producer layer, model-dependent**
   - Runs anomaly detectors/classifiers/segmenters when available.
   - May require datasets, checkpoints, GPU/CPU runtime, thresholds, and manual
     environment setup.
   - Produces normalized model-output records, not `Evidence`.
2. **Evidence adapter layer, model-independent**
   - Consumes model-output records, dataset labels, masks, wafer maps, captions,
     and deterministic descriptors.
   - Produces validated `Evidence`.
   - Never writes root cause, ranked paths, or `kg_analysis`.

This gives a clean "front connects to back" structure:

```text
Option C producer outputs
-> Option B evidence adapter
```

Practical consequence:

- The immediate agent-implementable work is the evidence adapter layer.
- Model producers can be added later without rewriting the Evidence adapter
  contract.
- In paper language, "adapter" can mean the full ingestion subsystem, but code
  should keep producer and evidence adapter modules separate.

Suggested naming:

- `kgtracevis.producers.*` or `kgtracevis.adapters.producers.*` for
  model-dependent producers.
- `kgtracevis.adapters.*` for model-independent Evidence adapters.

## Key Design Decision

The ingestion subsystem can sit at different levels of responsibility:

1. Convert already-computed records/model outputs into Evidence.
2. Also compute geometry/descriptors from masks/wafer maps.
3. Also run ML inference.

The project should decide how much responsibility belongs in the immediate
model-independent Evidence adapter, and how much is deferred to model-dependent
producers.

## Option A: Record-Only Evidence Adapter

### How it works

Adapters accept structured records only. Upstream scripts/models provide fields
such as:

- MVTec: `object`, `defect_type`, `anomaly_score`, `mask_path`, `bbox`,
  `morphology`, `location`, `caption`.
- WM811K: `failure_pattern`, `confidence`, `wafer_map_path`, `zone`,
  `morphology`, `defect_density`.

The adapter maps those fields to `Evidence` and observations.

### Pros

- Fastest to implement.
- Very low dependency and runtime risk.
- Fits existing `batch.py` and `generate_evidence.py`.
- Easy to test.

### Cons

- Does not prove we can derive evidence from masks/maps ourselves.
- Paper reviewer may ask whether evidence fields were manually prepared.
- Weakest demonstration of adapter contribution.

### Best use

- Smoke-test baseline.
- First PR only, not final adapter story.

## Option B: Record + Deterministic Feature Evidence Adapter

### How it works

Adapters accept structured records plus paths/arrays for masks or wafer maps.
They derive deterministic evidence when explicit fields are absent.

MVTec derivations:

- mask/heatmap threshold -> anomaly region,
- area ratio -> severity,
- centroid -> center/edge/surface/location,
- bounding box/eccentricity -> linear/spot/dense morphology,
- caption/DS label -> defect/anomaly type when available.

WM811K derivations:

- wafer map label/classifier output -> anomaly type / spatial pattern,
- failed die ratio -> severity,
- centroid/radial distribution -> center/edge/ring/local location,
- connected components / density / line fit -> morphology,
- map shape and descriptor stats -> raw provenance.

### Pros

- Best balance of feasibility and research value.
- Uses existing project dependencies (`numpy`, `pandas`; optional `opencv`,
  `Pillow`, `scikit-image` under `vision` extra).
- Demonstrates adapter evidence generation, not just field renaming.
- Deterministic and reproducible.
- Avoids training or bundling large models.

### Cons

- Need clear rules and tests.
- Geometry heuristics can be imperfect and must be described as evidence
  extraction, not ground truth.
- Requires small KG expansion so derived terms link correctly.

### Best use

- Recommended v0 path.
- Good enough for adapter-first paper milestone.

## Option C: Model-Inference Producer

### How it works

Producer modules run ML inference before the Evidence adapter:

- MVTec: Anomalib PatchCore/EfficientAD produces `pred_score`,
  `anomaly_map`, `pred_label`, optionally `pred_mask`.
- WM811K: CNN/ResNet/EfficientNet/ViT classifier predicts failure pattern and
  confidence; optional Grad-CAM/attention map provides saliency.

The Evidence adapter then converts producer outputs into Evidence.

### Pros

- Most end-to-end and visually convincing.
- Better story for "raw image/map -> evidence".
- Could support stronger demos later.

### Cons

- Highest engineering cost.
- Training/checkpoint/data management can dominate the project.
- Introduces more dependencies and reproducibility risk.
- Not necessary to prove the KGTraceVis evidence adapter contract.

### Best use

- Later milestone after deterministic evidence adapter path is stable.
- Keep as an optional producer, not inside core Evidence adapter logic.

## Recommended Choice

Choose **Option B for the evidence adapter layer**, with Option A-compatible
records as the immediate fallback and Option C as a deferred producer layer.

Recommended split:

```text
PR1: model-output record contracts and fixtures
PR2: deterministic Evidence adapters for MVTec masks/geometry and WM811K wafer maps
PR3: adapter-to-pipeline script and top-k path summaries
PR4: optional producer-output readers
PR5: model-dependent producers when data/checkpoints/environment are ready
```

## Dataset-Specific Recommendation

### MVTec / DS-MVTec

Recommended immediate evidence adapter mode:

> Record + deterministic feature adapter.

Input contract:

- Required: `case_id`, `object/category`, `defect_type` or `label`.
- Preferred: `mask_path` or mask array/statistics, `heatmap_path` or anomaly
  map statistics, `anomaly_score`, `caption`.
- Optional: `bbox`, `centroid`, `area`, `eccentricity`, detector metadata.

Output:

- `dataset="mvtec"`, `source="image"`.
- observations: object, anomaly_type, location, morphology, severity,
  confidence.
- raw evidence: image/mask/heatmap/caption/detector provenance.
- adapter never writes root cause or top-k paths.

Decision detail:

- Use explicit record fields if present.
- Else derive location/morphology/severity from mask/geometry.
- Use caption/DS label for anomaly type, but keep VLM/caption-only evidence
  lower confidence.

Future producer layer:

- PatchCore/EfficientAD/anomaly detector producer may emit a model-output record
  containing `pred_score`, `anomaly_map_path`, `mask_path`, `bbox`, and
  `detector_metadata`.
- The MVTec Evidence adapter consumes that record exactly like a manual or
  fixture record.

### WM811K

Recommended immediate evidence adapter mode:

> Record + deterministic wafer-map descriptor adapter.

Input contract:

- Required: `case_id`, `failure_pattern`/`label` or classifier prediction.
- Preferred: `wafer_map` array or `wafer_map_path`, `confidence`, `wafer_id`.
- Optional: `map_shape`, `die_count`, `failed_die_count`,
  `defect_density`, `zone`, `descriptor_stats`, `saliency_path`.

Output:

- `dataset="wafer"` in schema.
- `adapter.name="wm811k"` or `adapter.metadata["source_dataset"]="wm811k"`.
- top-level `anomaly_type` should contain the canonical pattern so current
  linker/path-ranker can start from it.
- optional `spatial_pattern` observation for UI/metrics.
- raw evidence extra stores original WM811K class label and descriptor stats.

Decision detail:

- Keep public WM811K as pattern/evidence analysis, not verified process RCA.
- Map WM811K classes into KG anomaly nodes and plausible explanation nodes only
  when source/evidence/confidence/review_status are explicit.

Future producer layer:

- A CNN/ResNet/EfficientNet/ViT producer may emit a model-output record
  containing `predicted_pattern`, `confidence`, `saliency_path`, and optional
  descriptor stats.
- The WM811K Evidence adapter consumes that record and does not care which model
  produced it.

## Decisions Needed From User

### Decision 1: Ingestion Architecture

Options:

1. **Single adapter does everything** - simpler naming, but mixes ML inference
   and Evidence contract; not recommended.
2. **Two-layer ingestion: producer -> Evidence adapter** - recommended; keeps
   model-dependent work separable and lets agents implement the back half now.

### Decision 2: WM811K Schema Identity

Options:

1. **Use `dataset="wafer"` and `adapter.name="wm811k"`** - recommended; least
   schema churn.
2. Add `dataset="wm811k"` to schema - clearer name, but touches schema, KG
   scenario validation, tests, docs, and likely CSV conventions.

### Decision 3: First Milestone Scope

Options:

1. **Two small cases per dataset** - one clean and one noisy/correction case;
   fastest full loop.
2. 10-20 records per dataset - better experiment shape but more KG/reference
   work.
3. Full dataset batch support - not recommended before the adapter contract and
   KG path support are stable.
