# TEP RCA provider selection slice

## Decision

The next slice should not change the RCA engine. It should expose a small provider-selection helper and connect it to existing entry points.

## Entry points to consider

* `src/kgtracevis/experiments/adapter_pipeline.py`
* `scripts/run_adapter_pipeline.py`
* `scripts/run_examples.py`
* `src/kgtracevis/service/runs.py`
* `src/kgtracevis/service/handlers.py`

## Desired behavior

Default behavior remains unchanged. Users must explicitly opt into:

* `native` for `TepNativeRcaProvider`
* `artifact` for `TepRcaArtifactProvider`

The helper should be reusable so CLI, service, and tests do not duplicate provider construction rules.

## Constraints

* No separate route2.
* No hard-coded paths into `/Users/hhm/code/TEP_KG` or `/Users/hhm/code/RootLens`.
* Artifact provider requires an explicit artifact path.
* Native provider can rely on the runtime graph passed by `KGTracePipeline`.
