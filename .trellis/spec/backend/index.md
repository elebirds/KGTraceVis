# Backend Development Guidelines

KGTraceVis is a uv-managed Python research prototype for knowledge-enhanced
industrial anomaly evidence analysis and RCA.

## Pre-Development Checklist

Before writing backend code:

1. Read the relevant backend spec file below.
2. Confirm reusable logic belongs under `src/kgtracevis/`.
3. Confirm scripts/apps/services will call the reusable pipeline instead of
   duplicating logic.
4. Check whether the change touches KG CSV contracts, evidence JSON contracts,
   or RCA path output contracts.
5. If adding KG knowledge, verify every edge has source, evidence, confidence,
   weight, review status, and feedback counters.

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | Active |
| [Database Guidelines](./database-guidelines.md) | KG CSV, in-memory graph, and Neo4j conventions | Active |
| [Error Handling](./error-handling.md) | Validation and ambiguity handling | Active |
| [Quality Guidelines](./quality-guidelines.md) | Test, lint, and traceability rules | Active |
| [Logging Guidelines](./logging-guidelines.md) | Script output and future logging boundaries | Active |

## Quality Check

Run at minimum:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/run_examples.py
```

If Neo4j code changed, also run the Neo4j import/example commands documented in
`quality-guidelines.md`.

## Core Project Invariants

- The reusable pipeline is the product.
- The KG is task-oriented, not a giant general-purpose industrial KG.
- LLMs may suggest candidates but are not industrial authorities.
- MVTec RCA labels are curated plausible references, not native verified
  factory root causes.
- Feedback compatibility matters: correction candidates, paths, and KG edges
  need stable IDs or stable references.
