# real model smoke pipeline

## Goal

Get a practical, local end-to-end smoke path working:

```text
sample image / wafer map
-> pre-trained or ready-to-run model
-> producer-output record
-> Evidence adapter
-> KGTracePipeline
-> candidate / plausible problem paths
```

The intent is to make the project usable by a non-specialist who wants to run
something now, without training a new model first.

## Current Hypothesis

- MVTec should be exercised through a pre-trained anomaly detector backend
  exposed by Anomalib or a compatible exported checkpoint.
- WM811K should be exercised through a pre-trained or already-fit classifier
  checkpoint.
- The project should stay within the existing producer -> adapter -> pipeline
  architecture.

## Non-Goals

- Training new models.
- Claiming verified root cause.
- Changing the KG schema.
- Introducing a new top-level application or workflow.

## Acceptance Criteria

- A local environment can install the required runtime dependencies.
- A real model or a realistic local fallback can produce producer-output
  records for at least one MVTec sample and one WM811K sample.
- Those records can be converted into `Evidence` and analyzed by
  `KGTracePipeline`.
- The resulting outputs clearly stay in candidate / plausible explanation
  scope.
- The work is committed incrementally so each meaningful step is visible in git.

## Working Plan

1. Establish the smallest dependency set needed for the smoke path.
2. Confirm a runnable MVTec backend and a runnable WM811K backend.
3. Wire or document a single command for each path.
4. Verify the outputs end-to-end.

