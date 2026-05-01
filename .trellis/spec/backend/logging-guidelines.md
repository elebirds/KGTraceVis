# Logging Guidelines

KGTraceVis currently uses lightweight script output instead of a structured
logging framework. Keep this simple until a service or long-running experiment
runner needs richer logs.

## Current Pattern

- CLI scripts print concise progress summaries.
- Core library functions should not print during normal execution.
- Tests should assert returned data, not parse logs.

Example:

```python
print(
    "analyzed "
    f"{path}: case_id={evidence.case_id}, "
    f"linked={len(result.linked_entities)}, "
    f"consistency={result.consistency_score}, "
    f"paths={len(result.top_k_paths)}"
)
```

This pattern is used in `scripts/run_examples.py`.

## What To Log Or Print

For scripts:

- input file or case ID,
- number of validated/analyzed examples,
- consistency score,
- number of linked entities,
- number of returned paths,
- output path when writing files.

For future experiment runners:

- config path,
- random seed,
- noise level,
- metric output path,
- summary metrics.

## What Not To Log

- Full raw datasets.
- Secrets or credentials from `.env`.
- Long evidence payloads by default.
- Full stack traces in user-facing app views.

## Future Service Pattern

When FastAPI or another service layer becomes active:

- Use Python `logging`.
- Log request/case IDs and high-level status.
- Keep core modules free of logger configuration.
- Configure log formatting at the application boundary.

## Common Mistakes

- Printing inside reusable core functions such as `KGTracePipeline.analyze()`.
- Logging entire raw evidence blobs when only a case ID is needed.
- Treating logs as experiment artifacts; metrics and configs should be written
  as structured files under `runs/` or `outputs/`.
