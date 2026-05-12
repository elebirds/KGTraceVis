# brainstorm: research WM811K model evidence integration

## Goal

Bring WM811K model integration up to the same practical completeness as the current
MVTec path, so wafer-map classifier outputs can be converted into unified Evidence
JSON and then consumed by entity linking, consistency checking, correction, and RCA
path ranking.

## What I already know

* The user wants a WM811K model-integration investigation, especially for producing
  evidence data that supports later RCA.
* KGTraceVis already has a WM811K producer/adaptor path:
  `build_wm811k_records` reads pandas-readable WM811K tables and emits
  `dataset="wafer"`, `adapter="wm811k"` records.
* The existing WM811K adapter maps producer records to unified Evidence with
  `dataset="wafer"`, `object="wafer"`, `anomaly_type`, derived location,
  morphology, severity, observations, and WM811K provenance under
  `raw_evidence.extra["wm811k"]`.
* Existing backend wrappers support trusted local sklearn/joblib classifiers and a
  PyTorch ResNet34 checkpoint via `SklearnWM811KBackend` and
  `TorchWM811KBackend`.
* Current code already references the public Hugging Face model
  `radai-agent/radai-wm811k-defect-detection` and file
  `best_radai_resnet.pt`, including a `wm811k-resnet` model asset option.
* Public WM811K model evidence is classification evidence only. It must not be
  treated as verified root cause, and it should not inject RCA outputs into producer
  records.

## External Research Notes

* Kaggle hosts the common `LSWMD.pkl` WM-811K table and references the original
  IEEE TSM dataset paper by Wu, Jang, and Chen.
* The public `radai-agent/radai-wm811k-defect-detection` Hugging Face model card
  describes a ResNet34 wafer-map classifier trained on the full labeled defect
  subset, with 8 defect classes: Center, Donut, Edge-Loc, Edge-Ring, Loc, Random,
  Scratch, Near-full. It reports 64x64 grayscale input and `best_radai_resnet.pt`.
* Recent literature still treats WM811K as a wafer-map defect-classification
  benchmark, with heavy class imbalance and common preprocessing that removes
  `None`, normalizes maps, and resizes to 64x64. This supports a defect-only
  classifier boundary but also means normal/unlabeled handling must remain explicit.

## Assumptions (temporary)

* MVP should reuse the existing `TorchWM811KBackend` shape instead of adding a new
  deep-learning architecture.
* `wm811k-resnet` should be the default real model preset for WM811K because it has
  a public checkpoint whose architecture matches the repository wrapper.
* A sklearn backend remains useful for local baselines and smoke tests, but it is
  not the recommended public default.
* RCA support should come from stable observed evidence fields and KG constraints,
  not from model-generated causal claims.

## Requirements (evolving)

* Provide a documented WM811K model preset/download path parallel to MVTec model
  assets.
* Ensure WM811K producer records preserve model provenance:
  backend, checkpoint path/hash when local, source repo/file when downloaded,
  confidence, class list, and source table row.
* Ensure generated evidence includes:
  anomaly type/failure pattern, derived wafer location, morphology, severity or
  defect density, confidence, observations, native label provenance, and optional
  wafer/saliency artifact paths.
* Preserve the defect-only boundary:
  the public ResNet emits 8 defect classes and does not model `None`; unlabeled or
  normal rows should be filtered or explicitly marked, not silently coerced.
* Keep root-cause and path-ranking keys filtered from producer records.
* Add/keep tests for downloader asset selection, torch checkpoint loading,
  producer-record shape, adapter Evidence conversion, and end-to-end adapter
  pipeline smoke.

## Acceptance Criteria (evolving)

* [x] A developer can download the public WM811K ResNet checkpoint with a documented
      command.
* [x] A developer can build WM811K producer records from `LSWMD.pkl` or another
      pandas-readable table using `--model-backend torch-resnet34`.
* [x] Generated WM811K records convert to schema-valid Evidence and carry sufficient
      observed fields for RCA pipeline stages.
* [x] The implementation documents that WM811K model outputs are defect-pattern
      evidence, not verified root-cause labels.
* [x] Tests cover the selected model path without requiring network or real
      checkpoint access in normal CI.

## Definition of Done (team quality bar)

* Tests added/updated where appropriate.
* `uv run --extra dev pytest` passes.
* `uv run python scripts/run_examples.py` passes.
* Docs/notes updated if user-facing behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope

* Training a new WM811K model from scratch.
* Claiming verified industrial root causes from WM811K labels.
* Adding unsupported wafer causal KG edges.
* Building a full human-in-the-loop wafer review workflow.
* Committing raw WM811K tables, generated records, or downloaded checkpoints.

## Technical Notes

* Existing files inspected:
  `src/kgtracevis/producers/backends.py`,
  `src/kgtracevis/producers/wm811k_records.py`,
  `src/kgtracevis/adapters/wm811k_adapter.py`,
  `src/kgtracevis/producers/model_assets.py`,
  `scripts/build_dataset_records.py`,
  `scripts/download_model_assets.py`,
  `scripts/run_real_model_pipeline.py`,
  `docs/dataset_record_producers.md`,
  `README.md`,
  `tests/test_record_producers.py`,
  `tests/test_service_api.py`.
* External sources:
  `https://huggingface.co/radai-agent/radai-wm811k-defect-detection`,
  `https://huggingface.co/radai-agent/radai-wm811k-defect-detection/tree/main`,
  `https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map`,
  `https://www.mdpi.com/2072-666X/17/3/309`.

## Real Smoke Run

* Ran real WM811K inference with local public checkpoint:
  `runs/real_model_pipeline/assets/wm811k/checkpoints/best_radai_resnet.pt`.
* Input table:
  `runs/real_model_pipeline/assets/wm811k/input_tables/test.pkl`.
* Command output:
  `runs/wm811k_real_recognition_smoke/wm811k_records.jsonl`.
* Adapter pipeline output:
  `runs/wm811k_real_recognition_smoke/adapter_pipeline/`.
* Result: 5 records produced and 5 Evidence files generated. All five sampled
  rows were predicted as `Loc`, matching their native WM811K label, with
  classifier confidences around `0.646` to `0.671`.
* Evidence boundary verified: generated Evidence has `adapter.produces_root_cause=false`
  and empty input `kg_analysis.top_k_paths`; RCA paths appear only in the adapter
  pipeline runtime summary.
* Follow-up gap: the current wafer KG only includes `NearfullDefect`, so runtime
  entity linking maps `loc` fuzzily to `NearfullDefect`. Before treating WM811K
  RCA paths as meaningful for all classes, add source-supported wafer KG entities
  and constraints for the eight public defect classes.

## Portable Download Smoke Run

* Added a portable WM811K data channel through:
  `uv run python scripts/download_model_assets.py --model wm811k-resnet --include-wm811k-data`.
* Defaults:
  model `radai-agent/radai-wm811k-defect-detection` / `best_radai_resnet.pt`;
  data `lslattery/wafer-defect-detection` / `test.pkl` with
  `repo_type="dataset"`.
* Verified actual command against:
  `runs/wm811k_portable_download_check/`.
* Verified producer smoke from the freshly downloaded assets with `--max-cases 2`;
  output:
  `runs/wm811k_portable_download_check/wm811k_records.jsonl`.
* Independent check passed lint, type-check, full pytest, examples, and confirmed
  the producer output remains observed wafer evidence with no root-cause claims.
