# Handoff for WebGPT Pro: Evidence-Centered RCA Framework Writing for RootLens

This handoff is meant to be pasted into WebGPT Pro to help draft and refine
Chapter 4, `Evidence-Centered RCA Framework`, of a ChinaVis 2026 paper. It
summarizes the implemented KGTraceVis backend, scripts, schema, KG construction
pipeline, and runtime reasoning contract so the draft can be grounded in the
actual system rather than in generic architecture language.

## Task for WebGPT Pro

Help write `sections/04-evidence-centered-rca-framework.tex` for the paper below.

Expected output:

1. A concise method-level explanation of the RootLens evidence-centered RCA
   framework.
2. A reviewer-facing outline of Chapter 4 with 4-5 subsections.
3. A LaTeX draft for `\section{Evidence-Centered RCA Framework}`.
4. Optional figure/table suggestions for this chapter: architecture pipeline,
   evidence schema table, KG edge/provenance table, and RCA reasoning flow.
5. A list of implementation facts that should be cross-checked before final
   submission.

Important constraints:

- Write in academic English, suitable for a short ChinaVis/VIS-style system
  paper.
- Target length: about 1.2-1.6 pages in an 8-page paper, excluding figures.
- Do not invent algorithms or industrial facts not supported by this handoff.
- Frame RootLens as a visual analytics and evidence-governance framework, not
  as a new anomaly detector.
- The chapter should explain the framework before the visual interface chapter.
  Avoid UI-specific details except where outputs are designed for visual review.
- Use cautious wording: candidate root-cause paths, plausible hypotheses,
  source-grounded evidence, reviewable outputs.
- Do not claim MVTec has verified factory root-cause labels.
- Do not claim LLM-extracted triples are trusted facts. In RootLens, LLM-style
  extraction is only a candidate-generation idea unless reviewed and
  source-attached.

## Paper Identity

Current title:

`RootLens: Visual Analytics for Multi-Source Industrial Anomaly Detection and Traceable Root-Cause Analysis`

System name:

`RootLens`

Repository / implementation name:

`KGTraceVis`

Venue / format:

- ChinaVis 2026 candidate full paper.
- VGTC/ChinaVis LaTeX template.
- Main file: `paper/main.tex`.
- Target chapter file: `sections/04-evidence-centered-rca-framework.tex`.

Keywords:

Industrial anomaly detection, Root-cause analysis, Visual analytics,
Knowledge graphs, Provenance, Human-in-the-loop analysis.

## Current Paper Structure

The current paper has this structure:

```latex
\input{sections/01-introduction}
\input{sections/02-related-work}
\input{sections/03-domain-problem-and-design-requirements}
\input{sections/04-evidence-centered-rca-framework}
\input{sections/05-visual-analytics-system}
\input{sections/06-case-studies-and-evaluation}
\input{sections/07-discussion-and-conclusion}
```

Chapter 4 should connect Chapter 3's design requirements to Chapter 5's visual
analytics system. It should answer: what data abstraction, knowledge supply
layer, and reasoning workflow make RootLens possible?

## Core Paper Story for Chapter 4

Industrial RCA workflows receive heterogeneous outputs: image anomaly maps,
sensor-variable contributions, wafer patterns, logs, source documents, process
tables, and expert curation. These outputs are hard to compare because each
detector or dataset exposes different fields. RootLens unifies them after
detection at the level of evidence, KG entities, source traces, confidence, and
reviewable candidate paths.

The framework is not a universal detector and not a universal causal model.
Instead, it defines a stable evidence contract and a source-grounded reasoning
pipeline:

```text
raw data / local model inputs
-> model-aware producer
-> producer-output records
-> model-independent Evidence adapter
-> unified Evidence JSON
-> KGTracePipeline
-> entity linking / consistency / correction / RCA path ranking
-> visual analytics, provenance review, and feedback targets
```

The key distinction is:

- Producers may run or summarize detectors/classifiers, but they emit normalized
  records.
- Evidence adapters convert those records into observed anomaly evidence.
- Adapters do not emit root causes, ranked paths, or prefilled KG analysis.
- `KGTracePipeline` computes linked entities, consistency scores, correction
  candidates, explanation paths, and ranked root-cause candidates at runtime.
- KG construction is a separate knowledge supply layer that builds and reviews
  source-grounded graph artifacts.

## Recommended Chapter 4 Shape

Keep the chapter mechanism-oriented. A strong outline would be:

### 4.1 Framework Overview

Explain the separation between evidence ingestion, source-grounded KG
construction, KG-based reasoning, and feedback-compatible outputs. Emphasize
why the evidence layer is the unification point across image, time-series, log,
and document sources.

### 4.2 Unified Evidence Representation

Describe the `Evidence` object and why `observations` are the canonical
reasoning contract. Explain that top-level fields provide an evidence envelope
and display metadata, while dataset-specific details stay under `raw_evidence`.
Make the adapter boundary explicit: observed evidence only, no root causes.

### 4.3 Source-Grounded Knowledge Supply

Describe task-oriented KG construction: registered sources, pluggable
extractors, reviewable draft entities/relations, CSV/Neo4j publication, and
edge-level provenance fields. Make clear that the KG is not a giant
general-purpose industrial KG.

### 4.4 Evidence-to-KG Reasoning

Describe the runtime sequence:

1. entity linking,
2. consistency checking,
3. correction candidate generation,
4. RCA reasoning and path ranking.

Include the relation-weighted score:

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

Explain that source edges and supporting evidence remain attached to each path.

### 4.5 Scenario-Aware RCA Plugins and Reviewable Outputs

Explain the unified RCA contract: generic graph-path reasoning for default
MVTec/wafer cases and a TEP Root-KGD provider for TEP. Both produce aligned
`top_k_paths` and `ranked_root_causes`. The outputs carry stable IDs,
supporting edges, scoring details, and review status so the visual system can
support inspection and feedback.

## Implementation Facts to Use

The following facts come from the current KGTraceVis repository and are safe to
use as implementation anchors.

### Evidence Schema

Implemented in:

- `src/kgtracevis/schema/evidence_schema.py`
- `docs/evidence_schema.md`

`Evidence` is a Pydantic model with these top-level fields:

```text
case_id
dataset
source
object
anomaly_type
location
morphology
severity
confidence
timestamp
raw_evidence
observations
adapter
normalized_evidence
kg_analysis
human_feedback
```

Supported datasets:

```text
mvtec, tep, wafer
```

Supported source types:

```text
image, time_series, log, multimodal, unknown
```

`RawEvidence` stores dataset-specific material such as:

```text
image_region
heatmap_path
variables
variable_contributions
log_events
description
extra
```

`EvidenceObservation` is the canonical observed-evidence unit used by KG
reasoning. Each observation includes:

```text
obs_id
facet
name
display_name
value
value_type
unit
direction
confidence
source_ref
raw_ref
time_window
metadata
```

Important writing point:

The paper should say that `observations` make evidence items stable and
referenceable. They allow a visual region, a sensor variable, a wafer spatial
pattern, or a log event to be linked and reviewed in the same reasoning layer.

### Adapter Boundary

Implemented in:

- `src/kgtracevis/adapters/ds_mvtec_adapter.py`
- `src/kgtracevis/adapters/tep_adapter.py`
- `src/kgtracevis/adapters/wm811k_adapter.py`
- `src/kgtracevis/adapters/batch.py`
- `docs/adapter_contracts.md`

Adapters are model-independent normalizers. They map producer records into
`Evidence` and set `adapter.produces_root_cause=false`.

MVTec / DS-MVTec adapter:

- Supports visual anomaly evidence such as object/category, anomaly score,
  heatmap path, mask geometry, bbox, centroid, area ratio, morphology,
  location, and severity.
- Detector outputs are treated as anomaly detection/localization evidence, not
  as semantic root-cause labels.
- If defect labels such as `crack` or `scratch` come from a folder or human
  prior, they should be described as native/operator label provenance, not as
  detector-inferred causes.

TEP adapter:

- Supports time-series/process evidence such as variables, variable
  contributions, fault/process metadata, process unit, time window, severity,
  and confidence.
- Emits variable observations with contribution values so the RCA provider can
  use current-sample evidence.

WM811K / wafer adapter:

- Supports wafer spatial-pattern evidence, location/zone, morphology, severity,
  confidence, wafer-map descriptors, and classifier metadata.
- Public WM811K supports spatial pattern evidence more directly than verified
  process RCA. Candidate paths should be framed as plausible explanations unless
  externally reviewed.

### Source-Grounded KG Construction

Implemented in:

- `src/kgtracevis/kg_construction/draft.py`
- `src/kgtracevis/kg_construction/extractors.py`
- `src/kgtracevis/kg_construction/pipeline.py`
- `src/kgtracevis/kg_construction/models.py`
- `src/kgtracevis/kg_construction/triple_cleaner.py`
- `src/kgtracevis/kg_construction/export_kg_csv.py`
- `docs/source_to_kg_construction_system.md`
- `docs/kg_construction.md`
- `docs/ontology_schema.md`

Method name:

```text
Source-Grounded Interactive KG Construction
```

The current construction layer separates:

```text
registered sources
-> extractor registry
-> draft entities and relations
-> cleaning / validation
-> candidate KG CSVs and construction manifest
-> review / future publication to runtime KG
```

`KGConstructionSource` includes:

```text
source_id
source_type
scenario
path
text
metadata
```

`DraftEntity` includes:

```text
draft_id
source_id
extractor_name
extractor_version
scenario
entity_id_suggestion
name
label
aliases
description
evidence
evidence_span
confidence
status
metadata
```

`DraftRelation` includes:

```text
draft_id
source_id
extractor_name
extractor_version
scenario
head
relation
tail
evidence
evidence_span
confidence
status
metadata
```

Draft statuses:

```text
draft, accepted, rejected, published
```

The current default extractor is a structured-record/manual-table extractor.
The methodology reserves room for LLM/document extractors, visual geometry
extractors, log extractors, and code extractors, but the paper should avoid
claiming a remote LLM KG builder is fully implemented unless that is verified
later.

### KG Schema and Runtime Graph

Implemented in:

- `src/kgtracevis/kg/graph.py`
- `src/kgtracevis/kg/import_neo4j.py`
- `data/kg/*.csv`
- `docs/ontology_schema.md`

Tracked KG nodes use:

```csv
id,name,label,scenario,aliases,description
```

Tracked KG edges use:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

Important paper point:

Every non-example edge is intended to be source-constrained and reviewable.
The edge schema carries the information needed for provenance inspection:
source, evidence text, confidence, weight, review status, and feedback counters.

The runtime graph supports scenario scoping:

```text
mvtec, tep, wafer, shared
```

For a selected evidence case, the runtime graph includes the case's scenario
and the shared layer.

### Core Runtime Pipeline

Implemented in:

- `src/kgtracevis/core/pipeline.py`
- `src/kgtracevis/core/rca.py`
- `src/kgtracevis/core/result.py`
- `src/kgtracevis/workflows/root_cause_provider_selection.py`

`KGTracePipeline.analyze(evidence, top_k=5)` runs:

```text
graph_for_evidence
-> link_evidence_entities
-> check_consistency
-> generate_correction_candidates
-> scenario-aware RCA reasoning
-> AnalysisResult
```

The pipeline loads a scenario-scoped KG snapshot from Neo4j by default, or uses
an explicit in-memory `KnowledgeGraph` when provided by scripts/tests.

`AnalysisResult` contains:

```text
case_id
linked_entities
consistency_score
inconsistent_fields
correction_candidates
top_k_paths
ranked_root_causes
human_feedback
```

### Entity Linking

Implemented in:

- `src/kgtracevis/kg/entity_linker.py`

The linker uses canonical observations first and falls back to compatibility
fields only when needed. Linkable facets include:

```text
object
anomaly_type
location
morphology
variable
log_event
```

The linker searches by exact ID, exact name, alias, partial match, and fuzzy
match. It returns top-k candidates and records ambiguity rather than silently
forcing low-confidence matches.

Each link payload includes:

```text
link_id
field
mention
selected_entity_id
score
match_type
ambiguous
ambiguity_margin
candidates
obs_id
facet
```

### Consistency Checking

Implemented in:

- `src/kgtracevis/kg/consistency_checker.py`

The consistency checker compares linked evidence fields against KG relation
rules. Current relation rules include:

```text
anomaly_type -> morphology: HAS_MORPHOLOGY
anomaly_type -> location: OCCURS_ON, HAS_LOCATION
variable -> location: MEASURED_IN, BELONGS_TO_UNIT
anomaly_type -> log_event: ASSOCIATED_WITH_EVENT
```

The checker returns:

```text
consistency_score
inconsistent_fields
checks
```

The score combines entity-link coverage and relation-rule pass rate.

### Correction Candidate Generation

Implemented in:

- `src/kgtracevis/kg/correction_generator.py`

Correction candidates are generated from KG neighborhoods when consistency
checks fail. Each candidate has a stable ID and supporting edge provenance.

Candidate fields include:

```text
candidate_id
source_field
source_entity_id
target_field
field
original_value
suggested_entity_id
suggested_value
score
reason
supporting_edge_ids
supporting_edges
```

Important writing point:

The pipeline does not mutate the original evidence. It presents correction
candidates as reviewable alternatives.

### Generic Relation-Weighted Path Ranking

Implemented in:

- `src/kgtracevis/kg/path_ranker.py`
- `src/kgtracevis/core/rca.py`

The generic path reasoner starts from linked source evidence entities and ranks
paths to root-cause-like targets. Current root-cause target labels include:

```text
RootCause
CauseCategory
FaultType
```

Path ranking uses:

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

Default weights:

```text
alpha = 0.55
beta = 0.35
gamma = 0.10
max_depth = 5
```

Each path includes:

```text
path_id
source_entity_id
target_entity_id
nodes
node_names
relations
score
confidence
evidence_match
length
supporting_evidence
source_edge_ids
source_edges
```

The path ID is stable, based on case ID, node sequence, and relation sequence.

### Unified RCA Output Contract

Implemented in:

- `src/kgtracevis/core/result.py`
- `src/kgtracevis/core/rca.py`
- `src/kgtracevis/workflows/root_cause_provider_selection.py`

Every RCA strategy should return:

```text
top_k_paths
ranked_root_causes
scoring_method
metadata
```

`RankedRootCause` includes:

```text
ranking_id
rank
candidate_id
candidate_name
candidate_label
candidate_role
score
confidence
evidence_match
explanation_paths
supporting_edges
supporting_evidence
scoring_method
scoring_details
source
review_status
```

The generic reasoner derives `ranked_root_causes` from ranked paths. The visual
system can therefore keep path inspection, root-cause candidate ranking, and
feedback targets aligned.

### TEP Root-KGD Provider

Implemented in:

- `src/kgtracevis/workflows/tep_root_kgd/__init__.py`
- `src/kgtracevis/workflows/tep_root_kgd/root_kgd.py`
- `src/kgtracevis/workflows/root_cause_provider_selection.py`
- `scripts/evaluate_tep_rca.py`

TEP uses `TepRootKgdRcaProvider` as the current domain-specific RCA adapter.
By default it is resolved through the `tep_root_kgd_default` reasoning profile
and called through the same `KGTracePipeline` output contract as the generic
graph-path adapter. Compatible profiles may be selected explicitly without
changing the RCA output schema.

The provider loads checked-in Root-KGD assets from:

```text
data/kg/tep_root_kgd/
```

Required asset files include:

```text
nodes.jsonl
edges.jsonl
tep_variable_mapping.jsonl
anchor_discriminators.json
relation_family_params.json
rca_edge_weights.jsonl
anchor_memory_profiles.json
```

Runtime scoring uses current Evidence's graph/variable contributions and
dynamic features. Fault numbers may be present as evaluation metadata, but the
provider metadata records:

```text
uses_fault_number_for_scoring = false
```

Important writing point:

TEP can be described as the current primary quantitative RCA scenario because
it has process-fault labels suitable for evaluation. However, fault labels
should be described as evaluation references, not scoring inputs.

### Service and Visual Analytics Boundary

Implemented/documented in:

- `src/kgtracevis/service/`
- `docs/rootlens_dashboard.md`
- `web/`

The service and dashboard consume pipeline outputs. They should not duplicate
entity linking, consistency checking, correction generation, or path ranking.

Run details expose:

```text
workflow steps
evidence summary
linked entities
correction candidates
top-k paths
path graph
visual evidence previews
source edge provenance
review targets
```

Feedback targets may include:

```text
path
edge
entity link
correction candidate
KG draft row
```

Review feedback is append-only application state. In the current foundation
version, it does not directly mutate KG CSV files.

## Scenario Boundaries for Writing

### TEP

Use as the strongest RCA reasoning case.

Safe wording:

- TEP provides process-variable evidence and process-fault references.
- RootLens maps variable contributions and dynamic features into a unified
  Evidence object.
- The TEP Root-KGD provider returns ranked root-cause candidates and support
  paths through the same output contract as the generic reasoner.
- Fault labels are used for evaluation, not as scoring inputs.

Avoid:

- "RootLens learns causal laws from TEP automatically."
- "The framework proves state-of-the-art RCA performance" unless final
  baselines and metrics are verified.

### MVTec / DS-MVTec

Use as visual evidence normalization and plausible explanation/case-study
support.

Safe wording:

- MVTec-style detectors provide image-level anomaly score, heatmap, mask, and
  geometry-derived evidence.
- RootLens can convert visual outputs into observations such as object,
  anomaly type or visual anomaly, location, morphology, severity, and
  provenance.
- Candidate paths for MVTec should be described as curated/plausible
  explanations, not verified factory root causes.

Avoid:

- "MVTec validates root-cause analysis."
- "MVTec defect class equals factory root cause."
- "PatchCore predicts semantic defect/root-cause labels."

### WM811K / Wafer

Use as wafer spatial-pattern evidence and possible traceability demonstration.

Safe wording:

- WM811K supports wafer spatial pattern evidence and classifier-output
  normalization.
- RootLens can represent wafer-map descriptors, zones, morphology, severity,
  and confidence in the same Evidence schema.
- Path outputs are candidate or plausible explanations unless backed by
  reviewed process records.

Avoid:

- "Public WM811K provides verified process root causes."

## Suggested LaTeX Content Blocks

WebGPT Pro may use these blocks as conceptual anchors, but should rewrite them
into polished paper prose.

### Framework Definition

RootLens defines RCA as an evidence-centered workflow rather than a
detector-specific prediction problem. Each case is represented as a set of
observed evidence items with source references, confidence, and optional
time/location metadata. A source-grounded KG supplies reviewable entities,
relations, and constraints. Runtime reasoning links evidence to KG nodes,
checks consistency, suggests corrections, and ranks candidate root-cause paths.

### Adapter Boundary

Adapters in RootLens normalize observed anomaly outputs only. They preserve
model and dataset provenance in `raw_evidence`, emit stable observations for KG
reasoning, and leave `kg_analysis` empty at ingestion time. Root-cause
candidates are produced later by the KG reasoning pipeline, preventing the
system from simply displaying prewritten answers.

### Provenance Boundary

KG edges are not treated as anonymous facts. Each edge carries source, evidence,
confidence, weight, review status, and feedback counters. This design allows a
candidate path to be inspected through its supporting edges and evidence text,
and allows future feedback to target the exact edge, path, correction, or entity
link under review.

### RCA Reasoning Boundary

RootLens supports scenario-aware RCA strategies behind a shared contract. For
general cases, relation-weighted path ranking combines KG edge confidence,
overlap with linked evidence, and a length penalty. For TEP, the Root-KGD
provider uses current variable contributions and dynamic features, but still
returns the same `top_k_paths` and `ranked_root_causes` fields. Thus the visual
workflow can compare and review RCA outputs across scenarios even when the
underlying reasoner differs.

## Figure and Table Suggestions

### Figure 4: Evidence-Centered RCA Framework

Suggested layers:

```text
Inputs
  images / masks / heatmaps
  time-series variables
  logs
  source documents / manuals / tables

Producer and Adapter Layer
  model-aware producers
  dataset adapters
  unified Evidence JSON

Knowledge Supply Layer
  source registry
  extractors
  draft KG
  reviewed/runtime KG

Reasoning Layer
  entity linking
  consistency checking
  correction generation
  RCA path ranking / scenario plugin

Review Output Layer
  linked entities
  inconsistent fields
  correction candidates
  top-k paths
  ranked root causes
  source-edge provenance
  feedback targets
```

### Table: Evidence Schema Summary

Columns:

```text
Group | Fields | Purpose | Example source
```

Rows:

```text
case envelope | case_id, dataset, source, timestamp | case identity and modality | upload/run metadata
observed anomaly | object, anomaly_type, location, morphology, severity, confidence | comparable evidence facets | detector or adapter output
raw provenance | raw_evidence.* | dataset/model-specific details | heatmap, variable contributions, logs
canonical observations | observations[*] | stable KG-linkable evidence items | region, variable, log event
analysis output | kg_analysis / AnalysisResult | runtime KG reasoning result | linked entities, paths, corrections
feedback | human_feedback / review targets | later review and correction | path/edge/entity decisions
```

### Algorithm Box: Runtime Evidence-KG Analysis

Pseudocode:

```text
Input: Evidence e, KG snapshot G, top_k
1. L <- link observations in e to candidate KG nodes in G
2. C <- check KG relation consistency among selected links
3. R <- generate correction candidates from failed checks and KG neighborhoods
4. P <- rank candidate RCA paths using relation confidence, evidence match, and length
5. Q <- project or compute ranked root-cause candidates from the selected RCA strategy
Output: linked entities L, consistency C, corrections R, top-k paths P, ranked causes Q
```

## Claims to Avoid or Weaken

Avoid writing:

- "RootLens solves industrial root-cause analysis."
- "RootLens discovers true causes across all modalities."
- "MVTec validates RCA accuracy."
- "LLM-extracted KG triples are reliable industrial facts."
- "Adapters infer root causes."
- "The KG is a complete industrial knowledge graph."
- "The visual system edits the production KG directly."

Safer wording:

- "supports traceable RCA workflows"
- "organizes heterogeneous anomaly evidence"
- "ranks candidate root-cause paths"
- "preserves source-grounded supporting edges"
- "presents plausible hypotheses for analyst review"
- "keeps evidence normalization separate from RCA reasoning"
- "treats KG construction outputs as reviewable candidate knowledge"

## Current Source Materials Used for This Handoff

Repository docs:

- `README.md`
- `docs/project_design.md`
- `docs/evidence_schema.md`
- `docs/adapter_contracts.md`
- `docs/source_to_kg_construction_system.md`
- `docs/ontology_schema.md`
- `docs/paper_experiment_protocol.md`
- `docs/rootlens_dashboard.md`

Core implementation files:

- `src/kgtracevis/schema/evidence_schema.py`
- `src/kgtracevis/adapters/ds_mvtec_adapter.py`
- `src/kgtracevis/adapters/tep_adapter.py`
- `src/kgtracevis/adapters/wm811k_adapter.py`
- `src/kgtracevis/core/pipeline.py`
- `src/kgtracevis/core/rca.py`
- `src/kgtracevis/core/result.py`
- `src/kgtracevis/kg/graph.py`
- `src/kgtracevis/kg/entity_linker.py`
- `src/kgtracevis/kg/consistency_checker.py`
- `src/kgtracevis/kg/correction_generator.py`
- `src/kgtracevis/kg/path_ranker.py`
- `src/kgtracevis/kg_construction/draft.py`
- `src/kgtracevis/kg_construction/extractors.py`
- `src/kgtracevis/kg_construction/pipeline.py`
- `src/kgtracevis/kg_construction/models.py`
- `src/kgtracevis/workflows/root_cause_provider_selection.py`
- `src/kgtracevis/workflows/tep_root_kgd/__init__.py`

Scripts and runtime entry points:

- `scripts/run_examples.py`
- `scripts/run_adapter_pipeline.py`
- `scripts/build_source_kg.py`
- `scripts/import_kg.py`
- `scripts/evaluate_tep_rca.py`
- `scripts/run_web_api.py`

## Final Instruction for WebGPT Pro

Please draft Chapter 4 now. Make the section read like a concrete implemented
framework, not a wish list. Explain the separation between adapters, KG
construction, KG reasoning, and visual review. Include the actual data fields
and output contracts where useful, but keep the prose compact and
reviewer-facing. Be conservative about claims: TEP is the main RCA case, MVTec
and WM811K should be described as visual/spatial evidence and plausible
traceability cases unless verified RCA references are provided.
