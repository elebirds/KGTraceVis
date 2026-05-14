# Project Design

KGTraceVis is organized around a producer-to-evidence-to-reasoning pipeline with
separate script and app clients.

The current runtime architecture is:

```text
raw data / local model inputs
-> model-aware producer
-> producer-output records
-> Evidence adapter / normalization
-> unified Evidence JSON
-> KGTracePipeline
-> linking / consistency / correction / path ranking
-> service / app / script consumers
```

KG construction is the knowledge supply layer for this reasoning architecture:

```text
registered sources
-> pluggable extractors
-> draft entities and relations
-> optional review/editing
-> versioned Neo4j KG
-> KGTracePipeline runtime reasoning
```

The detailed construction methodology is documented in
[`source_to_kg_construction_system.md`](source_to_kg_construction_system.md).
The important separation is that construction builds a source-grounded,
versioned runtime KG, while `KGTracePipeline` consumes that KG to analyze one
Evidence case at a time.

The core package under `src/kgtracevis/` owns schema validation, KG construction,
entity linking, consistency checking, correction generation, path ranking, noise
injection, metrics, and feedback-compatible result models.

Producer modules under `src/kgtracevis/producers/` are model-aware. They may run
detectors or classifiers over local raw data, but they emit normalized records,
not `Evidence`.

## Visual Anomaly Detection Scope

For MVTec-style image inputs, KGTraceVis treats Anomalib/PatchCore/STFPM-style
models as anomaly detectors and localizers, not defect-type classifiers. Their
trusted model outputs are image-level anomaly score/label, pixel-level anomaly
heatmap, predicted mask, and derived geometry such as area, centroid, location,
morphology, and severity.

MVTec folder names such as `crack`, `scratch`, or `contamination` are dataset or
operator labels. They may be stored as native label provenance or optional human
prior evidence, but they must not be represented as if the detector inferred the
defect type. When a user uploads a raw image without a reviewed defect label,
the system should keep `anomaly_type` as `unknown` or `visual_anomaly` and let
KG reasoning use the observed object, score, mask geometry, location,
morphology, severity, and provenance.

Adding a defect-type classifier is a later optional extension, not a requirement
for the v0 image-to-RCA flow. If introduced, it should be a separate semantic
candidate producer that emits reviewable `defect_type_candidates` with
confidence and source metadata. It should not replace the anomaly detector's
score/map/mask contract, and low-confidence semantic candidates should remain
editable before they influence KG reasoning.

Adapter modules under `src/kgtracevis/adapters/` are model-independent. They
convert producer-output records into the unified `Evidence` schema. Within that
schema, `observations` is the only canonical observed-evidence contract for KG
reasoning. Top-level fields describe the evidence envelope and display metadata;
`raw_evidence` stores source-specific raw details and provenance. Adapters do
not emit root causes, ranked paths, or prefilled `kg_analysis`.

`KGTracePipeline` is the reusable reasoning facade. It consumes validated
Evidence and writes runtime analysis outputs: linked entities, consistency
score, inconsistent fields, correction candidates, and top-k candidate paths.

Scripts under `scripts/` should only orchestrate these modules. The FastAPI
service under `src/kgtracevis/service/` should also call the same pipeline
APIs. The legacy Streamlit demo and old React/Vite frontend have been removed;
the future RootLens dashboard should be rebuilt cleanly against the FastAPI
backend.

For backend refactoring, KGTraceVis follows a workflow/use-case architecture
rather than a traditional MVC split. Scripts, FastAPI handlers, and experiments
should call reusable workflows under `src/kgtracevis/workflows/` for multi-step
producer, adapter, analysis, artifact, and run-session behavior. The target
architecture and migration rules are documented in
[`backend_workflow_refactor.md`](backend_workflow_refactor.md).
