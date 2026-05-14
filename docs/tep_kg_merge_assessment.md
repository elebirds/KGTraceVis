# TEP_KG Merge Assessment

This note analyzes `/Users/hhm/code/TEP_KG` as an external implementation sample
for KGTraceVis. It focuses on TEP graph construction logic, strengths, risks,
and the recommended merge strategy.

The local `TEP_KG` worktree contained many modified generated outputs during
inspection. This assessment is read-only and does not modify that repository.

## Executive Recommendation

Do not copy `TEP_KG` into KGTraceVis as-is.

Instead, merge it through a compatibility layer:

```text
TEP_KG extract/build concepts
-> KGTraceVis source-to-KG extractor plugins
-> KGTraceVis draft entity/relation IR
-> scenario=tep KG CSV/Neo4j contract
-> KGTracePipeline reasoning and future TEP workflows
```

The most valuable idea to preserve is the three-layer graph strategy:

```text
Full KG
-> Semantic Lift Layer
-> RCA Graph
```

KGTraceVis should generalize that as:

```text
Source Audit Graph
-> Runtime Semantic KG
-> Task-Specific Reasoning View
```

For v0 integration, KGTraceVis should import the TEP semantic/RCA knowledge as
scenario-scoped `tep` candidates, not as a replacement for the existing KG
contract.

## Current TEP_KG Construction Logic

The main entry point is `/Users/hhm/code/TEP_KG/scripts/build_kg.py`, which calls
`tep_kg.graph_build.build_kg(...)`.

The build performs these stages:

1. **Material governance**
   `build_governance(...)` inventories files under `materials/`, records asset
   IDs, hashes, content types, and status, then writes
   `data/processed/asset_catalog.jsonl`.

2. **Rule parsing**
   `parse_asset(...)` dispatches by file type:
   - MATLAB `.m` parser extracts functions, variable titles, setpoints, and
     loaded `.mat` assets.
   - C/header parser extracts functions, `#define`, and typedef-like symbols.
   - Simulink `.mdl` text parser extracts model names, signal nodes, callbacks,
     and source/destination blocks.
   - text/markdown parser extracts referenced files.
   - binary/PDF/MAT assets fall back to metadata-only parse records.

3. **Full KG conversion**
   Parsed records become `Entity`, `Evidence`, and `Triple` dataclasses. The
   full KG keeps implementation-level nodes such as `Module`, `Function`,
   `Parameter`, and `SignalNode`.

4. **Prior graph intake**
   `prior.py` adapts `data/external/prior/prior_graph.json` into normalized TEP
   equipment, stream, component, and variable entities. It maps raw relations
   such as `flows_to`, `measures_*`, and `controls_flow_of` into canonical
   relations and relation families.

5. **Entity resolution**
   `entity_resolution.py` collapses channel aliases such as `xmeas23`,
   `XMEAS_23`, `Plant Output 23`, `xmv_1`, and prior `MV_*` identifiers onto
   canonical TEP channel entities.

6. **TEP 52-channel mapping**
   `tep_variables.py` explicitly maps `xmeas_1..xmeas_41` and
   `xmv_1..xmv_11` to KG entities, producing a report that should be considered
   a high-value artifact for KGTraceVis.

7. **Semantic lift**
   `semantic_lift.py` projects the full KG into a smaller semantic backbone
   containing only `Equipment`, `Stream`, `Variable`, `Component`,
   `ControlLoop`, and `Fault`. It rewrites relation families into propagation
   relations such as `OBSERVED_BY`, `ACTS_ON`, and `HAS_COMPONENT`.

8. **RCA graph**
   `rca_graph.py` adds curated root-cause anchors, semantic concepts, and
   bridge relations to create a graph suited to Root-KGD-style propagation and
   ranking. It supports rule fallback and bounded LLM curation for semantic
   concepts.

9. **Exports**
   The build writes JSONL, CSV, GraphML, and Neo4j-admin CSV outputs for both
   the full KG and the RCA graph.

10. **RCA ranking stack**
    `propagation.py`, `root_kgd.py`, edge learning, and evaluation modules use
    the RCA graph for propagation, ranking, holdout evaluation, and metric
    reports.

Current inspected output summaries:

```text
Full KG:      706 entities, 3209 triples, 2723 evidence records
Semantic KG:   86 nodes,     85 edges
RCA Graph:    124 nodes,    213 relation instances by report counts
TEP mapping:  52/52 channels mapped
```

## Strengths To Reuse

### 1. Three-Layer Graph Design

`TEP_KG` avoids forcing one graph to serve every purpose. The full graph keeps
audit/debug detail; the semantic lift graph keeps process semantics; the RCA
graph keeps propagation-ready reasoning structure.

This should directly inform KGTraceVis:

```text
source audit / extraction graph
-> scenario runtime KG
-> reasoning view / path-ranking overlay
```

### 2. Evidence-Backed Dataclasses

`Entity`, `Evidence`, and `Triple` records preserve provenance IDs, source
types, confidence, and review status. This aligns strongly with KGTraceVis's
source-constrained KG philosophy.

### 3. Explicit TEP Variable Mapping

The 52-channel mapping is one of the strongest pieces. It bridges time-series
columns to KG entities, which is exactly what KGTraceVis needs for TEP evidence
linking and root-cause path ranking.

### 4. Relation Families

`relation_family` and `propagation_enabled` are useful additions. They separate:

```text
stored relation semantics
from
reasoning/propagation behavior
```

This is better than overloading relation names and should be adapted into
KGTraceVis path ranking and future TEP reasoning.

### 5. Rule-First, LLM-Bounded Design

TEP_KG uses rules for deterministic structure and limits LLM use to bounded
semantic curation with schema validation and fallback. This fits the KGTraceVis
principle that LLMs are adapters, not authorities.

### 6. Neo4j Export Awareness

It already exports Neo4j-admin CSV files and import manifests. The export shape
differs from KGTraceVis, but the idea of graph-specific publish artifacts is
useful.

## Weaknesses And Risks

### 1. Schema Incompatibility

TEP_KG uses:

```text
entity_id = variable:xmeas_1
entity_type = Variable
review_status = accept / needs_review / reject
provenance_ids = ev_...
```

KGTraceVis uses:

```text
id = PascalCase
label = Variable
scenario = tep
review_status = auto / reviewed / rejected
source + evidence as first-class edge columns
```

Direct copy would break existing KG loaders, QA, and Neo4j runtime queries.

### 2. Full KG Is Too Noisy For KGTracePipeline

The full KG contains many `Module`, `Function`, `Parameter`, `SignalNode`, and
asset nodes. Those are excellent for audit and drill-down, but too noisy for
default evidence linking and path ranking.

KGTraceVis should import either the semantic lift graph or a curated subset, not
the full graph as the runtime KG.

### 3. Review Semantics Are Too Coarse

`accept` in TEP_KG often means "rule accepted" or "prior accepted", not
necessarily human-reviewed. KGTraceVis should map:

```text
accept + rule/prior      -> reviewed only if source policy says so
accept + llm/rule mix    -> auto or reviewed depending on user review
needs_review            -> auto
reject                  -> rejected
```

This avoids accidentally upgrading generated TEP relations into reviewed facts.

### 4. Curated RCA Knowledge Lives In Python Constants

Root-cause anchors and curated bridges are embedded in `rca_graph.py`. They are
useful, but they should become source-registered draft relations in KGTraceVis,
not hidden facts in code.

### 5. Code Parsing Is Rule/Regex, Not AST

Despite supporting MATLAB, C, and Simulink files, parsing is regex-based. It is
good enough as a first extractor, but it should be named honestly as a
`RuleCodeExtractor`. A future `ASTCodeExtractor` can replace or augment it.

### 6. Generated Outputs Are Central To The Repo

TEP_KG tracks or mutates many generated outputs. KGTraceVis should keep runtime
exports under ignored `runs/`, `outputs/`, or `artifacts/` unless promoted as
small reproducible seed snapshots.

## Merge Strategy

### Phase 1: Import Concepts, Not Code

Document and adopt these concepts:

```text
Full KG / Source Audit Graph
Semantic Lift Layer / Runtime Semantic KG
RCA Graph / Task-Specific Reasoning View
relation_family
propagation_enabled
TEP 52-channel mapping
bounded LLM semantic curation
```

This phase is documentation and contract alignment only.

### Phase 2: Add TEP Extractor Adapters

Create KGTraceVis extractors that read TEP_KG outputs or source materials and
emit KGTraceVis draft IR:

```text
TepPriorGraphExtractor
TepVariableMappingExtractor
TepRuleCodeExtractor
TepSemanticLiftExtractor
TepRcaAnchorExtractor
```

The first practical extractor should be `TepVariableMappingExtractor`, because
it directly supports evidence linking from `xmeas_*` and `xmv_*` fields.

### Phase 3: Schema Mapping

Use a deterministic mapping layer:

| TEP_KG | KGTraceVis |
|---|---|
| `entity_id` | stable external ID in metadata plus KGTraceVis `id` |
| `entity_type` | `label` |
| no scenario field | `scenario=tep` |
| `aliases` | `aliases` |
| `triple.relation` | `relation` |
| `confidence` | `confidence` |
| `1 - confidence` | `weight` |
| `provenance_ids` | source/evidence expansion through evidence records |
| `accept` | `reviewed` or `auto` by policy |
| `needs_review` | `auto` |
| `reject` | `rejected` |
| `relation_family` | edge metadata or source evidence note initially |
| `propagation_enabled` | edge metadata or path-ranker policy input |

Because current KGTraceVis CSV edges do not have metadata columns for
`relation_family` and `propagation_enabled`, v0 can preserve them in evidence
text or draft metadata. A later schema extension can promote them to dedicated
runtime properties.

The first importer intentionally keeps only canonical machine aliases such as
TEP_KG external IDs and `tep_channel`. It does not import `full_kg_entity_ids`
as node aliases because those are TEP entity-resolution cluster members; treating
them as aliases can collapse deliberate `ALIGNS_TO` alias nodes and leave broken
edge endpoints. Free-text aliases from TEP_KG can include short Chinese
component names such as `组分 A`; the current KGTraceVis text normalizer is
ASCII-oriented and may collapse those to ambiguous single-letter identities.
Free-text alias import should wait for a Unicode-aware alias normalizer or a
stricter alias-review UI.

### Phase 4: Runtime KG Publish

Publish only a TEP semantic runtime graph to Neo4j:

```text
TEP semantic lift nodes
+ selected RCA anchors
+ selected propagation edges
-> KGTraceVis nodes/edges
-> scripts/import_kg.py or future KG publish workflow
```

The full TEP audit graph should remain accessible as source/draft artifacts or
a separate drill-down graph, not the default graph used by KGTracePipeline.

### Phase 5: Reasoning Integration

Connect TEP evidence to the imported graph:

```text
TEP evidence variable xmeas_7
-> entity linker candidates include Xmeas7 / xmeas_7 aliases
-> consistency/path ranking uses scenario=tep graph
-> path output records source edges and relation families
```

The Root-KGD propagation stack should be treated as a later reasoning workflow,
not merged into `KGTracePipeline` immediately.

## What To Merge Into KGTraceVis

Merge as reusable patterns:

- three-layer graph method;
- source/parse/evidence reports;
- TEP 52-channel mapping;
- relation family and propagation flags;
- bounded LLM curation pattern;
- semantic lift projection pattern;
- RCA graph as a task-specific view.

Merge as plugins/adapters:

- prior graph adapter;
- variable/channel mapping adapter;
- rule code parser adapter;
- semantic lift importer;
- RCA anchor importer.

Do not merge directly:

- TEP_KG's canonical schema as the global KGTraceVis schema;
- the full noisy implementation graph into default Neo4j runtime;
- Python-constant root-cause anchors as unreviewed hidden facts;
- Root-KGD ranking stack into `KGTracePipeline` before the KG provider and
  workflow layers stabilize.

## Concrete Next Steps

1. Add `tep_variable_mapping` as a registered source in KGTraceVis.
2. Implement a small `TepVariableMappingExtractor` that emits draft entities and
   alias relations for `xmeas_*` and `xmv_*`. This now exists in
   `src/kgtracevis/kg_construction/tep_import.py`.
3. Create a `TepSemanticLiftExtractor` that reads TEP_KG semantic lift JSONL and
   emits KGTraceVis draft nodes/edges. This now exists in
   `src/kgtracevis/kg_construction/tep_import.py`.
4. Add a mapping policy for review status and relation-family preservation.
5. Use `scripts/build_source_kg.py` to generate candidate CSV artifacts from
   TEP_KG semantic lift and variable mapping outputs.
6. Publish a minimal TEP semantic KG to Neo4j under `scenario=tep`.
7. Update TEP adapter evidence so variable mentions link to the published TEP
   KG entities.
8. Only after that, evaluate whether Root-KGD propagation becomes a separate
   `workflows/tep_rca.py` workflow or an optional path-ranker backend.
