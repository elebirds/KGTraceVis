# Source-to-KG Construction System

This document defines the KGTraceVis knowledge construction methodology.
It complements `docs/kg_construction.md`, which describes the existing CSV
contract and source-constrained construction rules.

The short name for the method is:

```text
Source-Grounded Interactive KG Construction
```

中文可称为：

```text
来源驱动的人机协同知识图谱构建体系
```

## Positioning

KGTraceVis does not aim to build a giant general-purpose industrial knowledge
graph. Its KG is a task-oriented knowledge asset that supplies the reasoning
pipeline with traceable entities, relations, aliases, constraints, and candidate
investigation paths.

The construction pipeline and reasoning pipeline are separate:

```text
Knowledge Construction Pipeline
  -> source management
  -> extraction
  -> draft KG
  -> review or direct publish
  -> versioned Neo4j KG

Reasoning Pipeline
  -> Evidence JSON
  -> entity linking
  -> consistency checking
  -> correction generation
  -> path retrieval and ranking
  -> explanation and feedback
```

The construction pipeline answers: **what knowledge is available and where did
it come from?**

The reasoning pipeline answers: **how does a particular evidence case behave
under the current KG version?**

## Core Principles

1. **Sources come first.**
   Knowledge must originate from a registered source: a dataset label table,
   adapter output, model record, text document, source-code file, SOP summary,
   manual curation table, log sample, or another explicit artifact.

2. **Extraction is modular.**
   LLM extraction is one extractor type, not the whole system. Structured data,
   visual geometry, wafer-map features, log records, and future code/AST
   extractors should plug into the same pipeline.

3. **Candidate knowledge uses one intermediate representation.**
   Every extractor should output the same draft entity/relation format before
   normalization, deduplication, review, and publication.

4. **Users control trust.**
   The system records source, evidence, confidence, and review status, but the
   user may decide whether to review candidates before use or publish them
   directly as low-confidence exploratory knowledge.

5. **Relation names express semantics; confidence expresses reliability.**
   The system should not over-encode trust by inventing many relation variants.
   A relation such as `CAUSES`, `AFFECTS`, or `RELATED_TO` expresses the user's
   intended semantics. The relation's `confidence`, `review_status`, `source`,
   and `evidence` express how reliable it is.

6. **The runtime KG is versioned.**
   Reasoning outputs must be reproducible against a known KG build/version,
   because entity linking and path ranking may change after sources or
   extractors are updated.

7. **Neo4j is the runtime interface.**
   CSV files remain useful as tracked seed data and reproducible snapshots, but
   the published runtime KG should be written to Neo4j for graph traversal and
   app queries.

## Source Layer

The source layer is the evidence warehouse for KG construction. A source is not
itself a KG fact; it is material from which candidate entities and relations may
be extracted.

Each source should have at least:

```text
source_id
title
source_type
scenario
path_or_url_or_ref
uploaded_by
created_at
description
usage_notes
```

Common source categories:

| Category | Examples | Typical KG Use |
|---|---|---|
| Dataset labels | MVTec object/defect labels, WM811K pattern labels, TEP fault labels | vocabulary, observed classes |
| Adapter/model outputs | Evidence records, anomaly masks, variable contributions, wafer classifier outputs | observed entities, morphology/location constraints |
| Official documents | dataset papers, benchmark descriptions, detector papers | task boundaries, label definitions, model-output semantics |
| Manual curation tables | expert notes, curated alias tables, relation spreadsheets | vocabulary, aliases, constraints, candidate relations |
| Text documents | SOP summaries, manuals, project notes, private safe summaries | terms, events, components, candidate relations |
| Logs and process records | alarms, events, recipe-step records | log-event vocabulary, event/process relations |
| Code assets | future TEP simulation or control code | variables, process units, dependency hints via AST extraction |

TEP code-file extraction is intentionally deferred until RootLens merge work,
but the methodology reserves it as a first-class source type. This is why the
extractor layer must be pluggable rather than LLM-only.

## Extraction Layer

Extractors convert sources into candidate knowledge. They do not publish KG
facts directly.

Recommended extractor types:

| Extractor | Input | Output | Notes |
|---|---|---|---|
| `StructuredRecordExtractor` | CSV/JSON/JSONL | entities, relations | deterministic; good for source tables and adapter records |
| `LLMTextExtractor` | markdown, text, PDF text, SOP summaries | entities, aliases, relation candidates, evidence spans | review-friendly; never treated as authority by default |
| `VisualGeometryExtractor` | mask geometry, bounding boxes, segmentation-derived features | morphology/location relations | good for MVTec-style evidence |
| `WaferPatternExtractor` | wafer maps, pattern classifier outputs | spatial signature, morphology, location relations | scenario-specific but same draft format |
| `LogEventExtractor` | alarm/event records | event vocabulary and event/process relations | future extension |
| `ManualKGExtractor` | user-edited tables | user-authored candidates | useful for controlled expert input |
| `ASTCodeExtractor` | TEP/source-code files | variables, functions, units, dependency hints | future RootLens/TEP extension |

The key design rule:

```text
Extractor implementation can vary.
Candidate knowledge output format must remain stable.
```

## Candidate Knowledge IR

All extractors should write a common candidate intermediate representation.

Draft entity:

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

Draft relation:

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
draft       generated but not acted on
accepted    user accepted or edited into usable form
rejected    user rejected; keep record to avoid repeated suggestions
published   written to the runtime KG
```

This draft layer is the main decoupling point between source extraction,
front-end review, CSV snapshots, and Neo4j publication.

## Construction Lifecycle

The full lifecycle is:

```text
1. Register source
2. Parse source
3. Select extractor
4. Extract candidate entities and relations
5. Normalize IDs, labels, aliases, relation names, and scenarios
6. Deduplicate against current draft and published KG
7. Detect conflicts and near-duplicates
8. Assign or preserve confidence
9. Present review queue
10. Accept, edit, reject, or skip review
11. Publish to Neo4j
12. Export versioned CSV/JSON snapshots
13. Make KG version available to reasoning pipeline
```

The user may skip step 10 for exploratory use. In that case the published
relations should still preserve low confidence, source provenance, and draft or
auto review status so downstream views can communicate uncertainty.

## Front-End Workspaces

A complete system should expose five workspaces.

### Source Library

Purpose: upload, register, inspect, and organize source materials.

Expected operations:

* add a source;
* edit source metadata;
* group by scenario and source type;
* view source coverage;
* mark private or summary-only sources;
* preserve source IDs used by KG edges.

### Extraction Workspace

Purpose: run a selected extractor over selected sources.

Expected operations:

* choose source(s);
* choose extractor type;
* inspect extraction run metadata;
* view candidate entities and relations;
* trace each candidate to an evidence span or source row.

### Draft KG Studio

Purpose: edit and prepare candidate knowledge before publication.

Expected operations:

* merge duplicate entities;
* edit names, labels, aliases, relation names, and confidence;
* inspect conflicts with existing KG;
* compare candidate relations against published relations;
* batch-update scenario or label assignments.

### Review Queue

Purpose: support human control without making review mandatory.

Expected operations:

* accept;
* edit and accept;
* reject;
* bulk accept low-risk vocabulary candidates;
* sort by low confidence, source type, relation type, graph impact, or conflict.

### Published KG / Neo4j Studio

Purpose: browse and manage the runtime graph.

Expected operations:

* filter by scenario, source, confidence, review status, relation, and label;
* inspect node/edge provenance;
* see which KG version is active;
* write published rows to Neo4j;
* export CSV snapshots for reproducibility.

## Review And Trust Model

Review is a control mechanism, not a hard requirement.

Suggested modes:

| Mode | Behavior | Use Case |
|---|---|---|
| Strict | only accepted/reviewed candidates can be published | stable experiments, paper assets |
| Pragmatic | draft and accepted candidates can be published, but confidence and status remain visible | prototype demos |
| Exploratory | extractor output can be written directly for rapid exploration | discovery and debugging |

Downstream reasoning can then choose a policy:

```text
use_all
reviewed_preferred
reviewed_only
confidence_threshold
scenario_scoped
```

This keeps user agency intact while still making uncertainty explicit.

## Relation Semantics And Confidence

Relations should not be split only to encode confidence. A relation name should
answer "what kind of semantic connection is being asserted?"

Examples:

```text
HAS_MORPHOLOGY
OCCURS_ON
BELONGS_TO
AFFECTS
CAUSES
RELATED_TO
PART_OF
```

Confidence and review metadata answer "how much should we trust this relation?"

```text
confidence=0.35
review_status=auto
source=llm_extraction
evidence=<source snippet>
```

The system may suggest safer wording in UI explanations, but it should not
force users to replace a semantic relation with a weaker duplicate relation
only because confidence is low.

## Publication To Neo4j

Publishing turns accepted or selected draft knowledge into runtime KG rows.

Neo4j nodes should preserve the current node contract:

```text
id
name
label
scenario
aliases
description
```

Neo4j relationships should preserve the current edge contract plus build
metadata when available:

```text
relation type
source
evidence
confidence
weight
review_status
feedback_count
accepted_count
rejected_count
draft_id
kg_build_id
created_by
created_at
updated_at
```

CSV remains a reproducible import/export artifact:

```text
published Neo4j KG
  -> export nodes.csv / edges.csv snapshot
  -> record kg_build_id and source/extractor versions
```

## KG Versioning

Every published KG build should record:

```text
kg_build_id
kg_version
published_at
source_ids
source_set_hash
extractor_versions
node_count
edge_count
review_policy
published_by
notes
```

Reasoning outputs should record:

```text
case_id
kg_build_id
linked_entities
source_edges
ranked_paths
confidence_policy
```

This is required for reproducible experiments and for explaining why a case's
ranked path changed after KG updates.

## Interface To The Reasoning Pipeline

The reasoning pipeline consumes a published KG, not raw sources.

```text
Evidence JSON
  -> KGTracePipeline
  -> Neo4jKGRepository scoped to [shared, dataset]
  -> entity candidates
  -> consistency constraints
  -> correction candidates
  -> candidate paths
  -> explanation with source edges
```

Construction quality affects reasoning quality:

* richer alias/vocabulary coverage improves entity linking;
* better morphology/location/process constraints improve consistency checking;
* better event/component/process relations improve candidate path retrieval;
* clearer provenance improves explanation and review.

The interface should stay stable even as extractor implementations change.

## Feedback Loop

Feedback from reasoning should feed the construction system:

```text
entity linking feedback
correction feedback
path feedback
KG edge feedback
```

Feedback can update review queues and confidence suggestions, but it should not
silently overwrite reviewed KG rows. Any confidence update rule should remain
deterministic and explainable in v0.

## MVP Scope

For the next implementation phase, the practical MVP is:

* keep current CSV seed KG and Neo4j import path;
* add source-management and draft-KG database models;
* expose source and draft management in KG Studio;
* support structured/manual and LLM-text extraction first;
* publish selected drafts to Neo4j;
* record `kg_build_id` on reasoning runs.

Deferred:

* TEP AST/code extraction;
* RootLens merge-specific extractor implementations;
* advanced conflict resolution;
* automatic confidence learning;
* large-scale source crawling;
* strong causal discovery.

## Implementation Roadmap

1. **Documentation and contracts**
   Define this methodology, draft entity/relation schemas, source metadata
   schema, and publication semantics.

2. **Backend data model**
   Store source records, source documents, extraction runs, draft entities,
   draft relations, review actions, and KG build metadata.

3. **Extractor registry**
   Add a Python registry where extractors declare source types, capabilities,
   version, and output schema.

4. **Source-to-draft endpoints**
   Add FastAPI endpoints for source upload/registration and extraction runs.

5. **KG Studio front-end**
   Add Source Library, Extraction Workspace, Draft KG Studio, Review Queue, and
   Published KG views using the existing Arco/ECharts workbench style.

6. **Neo4j publication**
   Publish selected drafts into Neo4j with scenario scoping, deduplication,
   provenance, and build metadata.

7. **Reasoning integration**
   Let analysis select a KG build and persist that build ID in analysis outputs.

8. **RootLens/TEP extensions**
   Add AST/code extraction and RootLens-specific source types after merge work.
