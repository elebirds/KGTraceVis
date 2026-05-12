# WM811K model options for evidence production

## Summary

The lowest-risk WM811K model integration path is to standardize around the
existing `torch-resnet34` backend and the public Hugging Face checkpoint
`radai-agent/radai-wm811k-defect-detection` / `best_radai_resnet.pt`.

This aligns with the current repository architecture:

* `TorchWM811KBackend` already builds a 1-channel ResNet34 classifier with an
  8-class head.
* `build_wm811k_records` already converts classifier outputs into producer
  records.
* `evidence_from_wm811k_record` already maps those records into unified wafer
  Evidence.
* `download_model_assets.py` and `model_assets.py` already have a
  `wm811k-resnet` asset entry in the current working tree.

## Candidate models

### Public ResNet34 checkpoint

Source: `https://huggingface.co/radai-agent/radai-wm811k-defect-detection`

Fit:

* Good match for current `TorchWM811KBackend`.
* Model card uses ResNet34, 64x64 grayscale wafer maps, and 8 defect classes:
  Center, Donut, Edge-Loc, Edge-Ring, Loc, Random, Scratch, Near-full.
* Files page exposes `best_radai_resnet.pt`, about 85 MB.
* Useful as the default real-model path for local demos and evidence generation.

Risks:

* The model card reports self-evaluated metrics; do not overclaim benchmark
  quality.
* It is defect-only and excludes `None`, so it should not be used as a normal
  wafer detector.
* It emits failure-pattern evidence only; no RCA claim should be emitted from
  the producer.

### Local sklearn/joblib classifier

Fit:

* Already supported by `SklearnWM811KBackend`.
* Useful for trusted local baselines, deterministic smoke tests, and custom
  tabular/feature experiments.

Risks:

* Shape compatibility depends on the exact flattened wafer-map dimensions used
  during training.
* Pickle/joblib loading is a trusted-local-file boundary only.
* Less suitable as a public out-of-the-box preset unless KGTraceVis ships a
  training recipe and model artifact.

### New CNN / hybrid / transformer models from literature

Fit:

* Recent papers explore CNN-ESN, lightweight CNN, CNN-transformer, autoencoder
  augmentation, and other imbalance-aware variants.
* These are useful future research candidates if the project needs robustness
  or rare-class evaluation.

Risks:

* Most do not provide a ready checkpoint matching this repo.
* Integrating them would expand scope into model training/reproduction.
* The value for KGTraceVis v0 is lower than getting a stable producer-to-Evidence
  path working with a public checkpoint.

## Evidence contract implications

WM811K evidence should emphasize observed and model-produced wafer-map fields:

* `anomaly_type`: canonicalized failure pattern, e.g. `edge_ring`, `nearfull`.
* `location`: deterministic wafer descriptor such as edge/center/local if
  derived from the map.
* `morphology`: deterministic spatial-pattern descriptor if available.
* `severity`: defect density or derived severity.
* `confidence`: classifier probability when provided.
* `raw_evidence.extra.wm811k`: source dataset, original pattern, annotation
  type, wafer id, map path or inline small map.
* `observations`: stable observed evidence rows for entity linking and
  consistency checking.
* `classifier`: backend, checkpoint, class list, and source metadata.

Do not include `root_cause`, `ranked_causes`, `top_k_paths`, or `kg_analysis`
in producer records.

## Recommended next implementation slice

1. Confirm the current `wm811k-resnet` downloader path is complete and covered
   by tests.
2. Add or document a WM811K model preset equivalent to MVTec's user-facing model
   story, if web/API selection is expected for wafer uploads later.
3. Add a smoke command that runs:
   download checkpoint -> build WM811K records -> convert to Evidence -> run
   adapter pipeline.
4. Explicitly document the defect-only boundary and the fact that RCA paths are
   later KGTracePipeline candidates, not WM811K labels.

## Sources

* Hugging Face model card:
  `https://huggingface.co/radai-agent/radai-wm811k-defect-detection`
* Hugging Face files page:
  `https://huggingface.co/radai-agent/radai-wm811k-defect-detection/tree/main`
* Kaggle dataset:
  `https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map`
* Recent WM811K robustness/preprocessing discussion:
  `https://www.mdpi.com/2072-666X/17/3/309`
