# Error Handling

KGTraceVis favors deterministic validation errors and explicit ambiguity records
over silent fallback behavior.

## General Pattern

- Public loaders validate required columns and referenced IDs.
- Invalid project data should raise `ValueError` with a concrete file or entity
  name.
- Optional infrastructure such as Neo4j should fail only when explicitly used.
- Entity linking should record unmatched or ambiguous candidates instead of
  throwing for ordinary low-confidence matches.

Examples:

- `KnowledgeGraph.from_csv()` raises when an edge references a missing node.
- `schema.validators.load_evidence_json()` lets Pydantic raise validation errors
  for invalid evidence JSON.
- `link_evidence_entities()` returns `selected_entity_id=None` for unmatched
  fields.

## Validation Matrix

| Condition | Behavior |
|---|---|
| Node CSV missing required columns | raise `ValueError` with missing column names |
| Edge CSV missing required columns | raise `ValueError` with missing column names |
| Edge head/tail not in loaded nodes | raise `ValueError` naming the missing node |
| Conflicting duplicate node ID | raise `ValueError` |
| Reviewed edge overwrite attempt | raise `ValueError` unless explicitly allowed |
| Evidence JSON invalid | Pydantic validation error |
| Entity mention unmatched | return unmatched link record |
| Entity mention ambiguous | return top-k candidates and `ambiguous=True` |

## API And Service Layer

`src/kgtracevis/service/` is currently a placeholder. When API handlers are
implemented:

- Catch validation errors at the service boundary.
- Return structured error responses without leaking stack traces.
- Do not swallow errors inside core modules if a caller needs to know that data
  is invalid.

## Wrong vs Correct

Wrong:

```python
try:
    graph = KnowledgeGraph.from_csv()
except Exception:
    graph = KnowledgeGraph([], [])
```

Correct:

```python
graph = KnowledgeGraph.from_csv()
```

Let invalid KG files fail fast during development and tests.

Wrong:

```python
selected = candidates[0]
```

Correct:

```python
if not candidates:
    return {"selected_entity_id": None, "match_type": "unmatched"}
```

Low-confidence evidence is expected in this project and must remain reviewable.
