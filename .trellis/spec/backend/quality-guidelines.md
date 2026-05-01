# Quality Guidelines

KGTraceVis prioritizes clarity, reproducibility, and traceability over complex
model design.

## Required Commands

Before submitting code changes, run:

```bash
uv run --extra dev pytest
uv run python scripts/run_examples.py
```

Also run lint and type-check when Python code or config changes:

```bash
uv run --extra dev ruff check .
uv run --extra dev mypy src tests scripts
```

If Neo4j-related code is modified, also run:

```bash
uv run python scripts/import_kg.py
uv run python scripts/run_examples.py --with-neo4j
```

## Test Expectations

Tests should cover behavior, not placeholders:

- schema validation,
- KG CSV loading and merge behavior,
- entity linking,
- consistency checking,
- correction generation,
- path ranking,
- noise injection,
- metric calculation.

Current examples:

- `tests/test_kg_graph.py`
- `tests/test_entity_linker.py`
- `tests/test_consistency_checker.py`
- `tests/test_path_ranker.py`
- `tests/test_pipeline.py`

## Coding Rules

- Use Python 3.10+ syntax.
- Use Pydantic for JSON schema validation.
- Use `uv` for dependency management.
- Use type hints where practical.
- Keep public functions documented with short docstrings.
- Keep core logic under `src/kgtracevis/`.
- Avoid hidden global state.
- Avoid hard-coded absolute paths.
- Read paths from config, arguments, or relative project defaults.

## KG Quality Rules

- Never add unsupported industrial facts.
- Every KG edge must include `source`, `evidence`, `confidence`, and
  `review_status`.
- Do not claim MVTec has native real root-cause labels.
- MVTec RCA edges are curated plausible reference edges unless formal review
  proves otherwise.
- Do not overwrite reviewed triples automatically.

## Lint Scope

Ruff applies to KGTraceVis source, tests, scripts, and project config. Trellis
and tool-generated scaffolding is excluded in `pyproject.toml`:

```toml
extend-exclude = [
    ".agents",
    ".claude",
    ".codex",
    ".cursor",
    ".opencode",
    ".trellis",
]
```

Do not "fix" generated Trellis files just to satisfy KGTraceVis lint.

## Wrong vs Correct

Wrong:

```python
# silently choose a weak match
return candidates[0]
```

Correct:

```python
# return top-k candidates and record ambiguity
return {
    "selected_entity_id": selected.entity_id,
    "ambiguous": selected.score - second_score < 0.08,
    "candidates": [candidate.model_dump() for candidate in candidates],
}
```

Wrong:

```python
# script owns reusable analysis logic
def rank_paths(...):
    ...
```

Correct:

```python
from kgtracevis.kg.path_ranker import rank_root_cause_paths
```

Scripts call reusable modules; they do not duplicate the core pipeline.
