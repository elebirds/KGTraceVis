# KG Construction

KG construction is source-constrained.

Candidate entities and triples may come from dataset labels, official tables,
curated project notes, SOP excerpts, or LLM-assisted extraction from provided
sources. LLM output is never treated as ground truth by default.

Each edge must keep its source, evidence text or row, confidence, weight, and
review status.

For the full source-to-KG methodology and future system design, see
[`source_to_kg_construction_system.md`](source_to_kg_construction_system.md).

## Construction Lifecycle

KGTraceVis treats KG construction as a reusable supply pipeline for the runtime
reasoning pipeline:

```text
source management
-> pluggable extraction
-> draft entities and relations
-> optional user review/editing
-> Neo4j publication
-> versioned KG consumed by KGTracePipeline
```

The current CSV files under `data/kg/` are seed and snapshot artifacts. The
runtime graph is imported into Neo4j for app and service queries, while CSVs
remain useful for reproducible examples, tests, and paper-facing exports.

## Source Types

Supported or planned source classes include:

- dataset labels and benchmark tables;
- adapter/model output records;
- mask geometry and wafer-map feature outputs;
- official papers and dataset documentation;
- manual curation tables;
- SOP/manual/log summaries;
- LLM-extracted candidates from provided text;
- future TEP/source-code files parsed by AST extractors.

All source types should converge to the same candidate entity/relation
intermediate representation before cleaning, review, and publication.

## User Control

Review is recommended but not mandatory. Users may publish unreviewed candidate
knowledge for exploratory analysis, provided the resulting KG rows keep their
source, evidence, confidence, and review status.

Relation names should express semantics such as `CAUSES`, `AFFECTS`,
`HAS_MORPHOLOGY`, or `BELONGS_TO`. Trust should be expressed through
`confidence`, `review_status`, source provenance, and downstream reasoning
policies rather than by forcing duplicate weak relation names.
