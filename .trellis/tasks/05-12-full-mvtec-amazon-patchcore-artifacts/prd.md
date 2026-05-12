# brainstorm: configure full MVTec Amazon PatchCore artifacts

## Goal

Make the backend configuration capable of managing official Amazon PatchCore
artifacts for all MVTec object classes, instead of requiring users to manually
point every run at a single object-specific directory such as `mvtec_bottle`.

## What I Already Know

- The `amazon-patchcore` backend can load one official artifact directory that
  contains `patchcore_params.pkl` and `nnscorer_search_index.faiss`.
- The official Amazon repo stores artifacts by object, e.g. `models/.../models/mvtec_bottle`.
- The currently downloaded and verified artifact is only `mvtec_bottle`.
- The verified `bottle` run used real Git LFS artifact contents, not pointer
  files. Full-class coverage still needs object-by-object artifact download and
  smoke validation.
- The image-upload path currently resolves one `checkpoint_path` and passes that
  path to the selected backend.
- `scripts/build_dataset_records.py` currently accepts a single `--checkpoint`
  path.
- Existing public asset helpers download Hugging Face files; they do not yet
  manage official Git LFS object-specific PatchCore artifacts.

## Assumptions

- We should not make full official PatchCore artifacts part of the default
  download, because Git LFS can be large and slow.
- MVP should add explicit support for a local official model root containing
  multiple `mvtec_<object>` directories, plus helpers to download selected or
  all object artifacts from an already cloned official repo.
- Runtime selection should map KGTraceVis object names such as `bottle`,
  `metal_nut`, and `toothbrush` to official directories such as
  `mvtec_bottle`, `mvtec_metal_nut`, and `mvtec_toothbrush`.

## Requirements

- Add a canonical list of MVTec object names supported by official Amazon
  PatchCore artifacts.
- Add helper logic to discover/resolve the correct object artifact under a root.
- Allow `amazon-patchcore` use cases to pass an artifact root rather than a
  single object directory where practical.
- Add a script or asset helper that can pull selected/all official object
  artifacts with Git LFS without smudging the entire repo.
- Keep the default lightweight path unchanged.
- Preserve the current claim boundary: PatchCore outputs anomaly score, heatmap,
  and mask-like localization only; it does not infer semantic defect classes.
- Document the official artifact contract clearly:
  - artifacts are object-specific, not one global MVTec model;
  - a full root contains one `mvtec_<object>` directory per supported object;
  - pointer-only Git LFS files must not be treated as downloaded artifacts;
  - `--object-checkpoint-root` and `KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT`
    point at the common root and resolve by object name;
  - macOS smoke runs may need OpenMP variables pinned.

## Acceptance Criteria

- [ ] A local root containing `mvtec_bottle`, `mvtec_capsule`, etc. can resolve
  object-specific Amazon PatchCore checkpoints deterministically.
- [ ] Missing object artifacts fail with actionable errors listing the expected
  path/object.
- [ ] CLI/service paths can use all-class official Amazon PatchCore
  configuration without hard-coding bottle.
- [ ] Tests cover object-name to artifact-dir resolution and missing-object
  failure behavior.
- [ ] Docs/spec mention that official artifacts are object-specific and that
  full-class coverage requires one artifact directory per MVTec object.
- [ ] Docs show Git LFS selected-object and all-object pull commands and explain
  how to detect pointer-only files.
- [ ] Docs show CLI `--object-checkpoint-root` usage and Web/API
  `KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT` root usage.
- [ ] Docs record that the selected official artifact root has now been
  downloaded for all 15 MVTec object classes, while true model-output
  validation beyond `bottle` is still pending.

## Definition of Done

- Tests added or updated.
- `uv run --extra dev pytest` passes.
- `uv run --extra dev ruff check .` passes.
- `uv run --extra dev mypy src tests scripts` passes if Python signatures change.
- `uv run python scripts/run_examples.py` still passes.

## Out of Scope

- Paper-grade full-MVTec evaluation.
- Automatically committing large official artifacts or generated run outputs.
- Treating PatchCore mask-derived location/morphology as high-confidence before
  calibration.

## Documentation Notes

The official artifact root should be documented as a directory of object
artifacts:

```text
<patchcore-artifact-root>/
|-- mvtec_bottle/
|   |-- patchcore_params.pkl
|   `-- nnscorer_search_index.faiss
|-- mvtec_capsule/
|   |-- patchcore_params.pkl
|   `-- nnscorer_search_index.faiss
`-- ...
```

Users should clone the Amazon repo with Git LFS smudge disabled, then pull only
the selected object artifacts or all `models/**` artifacts:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/amazon-science/patchcore-inspection.git
cd patchcore-inspection
git lfs install --local
git lfs pull -I "models/<run-name>/models/mvtec_bottle/**"
git lfs pull -I "models/**"
```

Pointer-only files start with `version https://git-lfs.github.com/spec/v1` and
must be pulled before the object is usable.

For CLI batch generation, use:

```bash
uv run python scripts/build_dataset_records.py --dataset mvtec \
  --model-backend amazon-patchcore \
  --object-checkpoint-root /path/to/<patchcore-artifact-root> \
  ...
```

For Web/API image upload, set:

```bash
export KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT=/path/to/<patchcore-artifact-root>
```

The service resolves that root by uploaded `object_name`, e.g. `bottle` maps to
`mvtec_bottle`.

On macOS, use the OpenMP guard variables for official Amazon PatchCore smoke:

```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
```

Current state: the selected official Amazon PatchCore artifact root
`IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models` has been pulled with Git LFS
for all 15 MVTec object classes. The local root occupies about 227 MiB and
`list_amazon_patchcore_artifact_dirs` resolves:
`bottle,cable,capsule,carpet,grid,hazelnut,leather,metal_nut,pill,screw,tile,toothbrush,transistor,wood,zipper`.

Full-class smoke validation has now run on a lightweight DS-MVTec input with one
`good` image and one defect image per object. The CPU run completed successfully:
30 producer records were generated, all 15 object-specific checkpoints were
loaded, every record includes score/heatmap/mask/mask_stats fields, and the
records completed the Evidence adapter plus KGTracePipeline summary/table path.
Outputs are under `runs/amazon_patchcore_full_class_smoke/`, especially
`full_class_smoke_summary.json`,
`mvtec_amazon_patchcore_records.jsonl`,
`adapter_pipeline/adapter_pipeline_summary.json`, and
`adapter_pipeline/adapter_pipeline_table.csv`.

Important caveat: an initial MPS run failed because PyTorch does not implement
this adaptive pooling case on MPS. CPU is the verified runtime for this smoke.
Also, official PatchCore raw scores are not calibrated to the KGTraceVis default
threshold of `0.5`: every sampled `good` image was still classified anomalous and
many masks cover nearly the full image. The model is therefore connected
end-to-end, but score calibration and mask threshold calibration are still needed
before treating classification or geometry evidence as reliable.

## Technical Notes

- Relevant files inspected:
  - `src/kgtracevis/producers/backends.py`
  - `src/kgtracevis/producers/model_assets.py`
  - `src/kgtracevis/producers/mvtec_models.py`
  - `src/kgtracevis/service/runs.py`
  - `scripts/build_dataset_records.py`
  - `.trellis/spec/backend/mvtec-model-presets.md`
