# brainstorm: run MVTec PatchCore on Defect Spectrum

## Goal

Run the existing MVTec PatchCore producer path on the locally downloaded
Defect Spectrum data under `/Users/hhm/Downloads/Defect_Spectrum`, then feed the
generated records through the MVTec Evidence adapter and KGTracePipeline.

## What I already know

* The user wants the first task to be getting PatchCore working for MVTec.
* The project already has MVTec model presets: `auto`, `patchcore`, `stfpm`, and
  `efficientad`.
* On this machine, `auto` currently resolves to `patchcore` because
  `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt`
  exists and EfficientAD is not available.
* MVTec producer outputs must remain observed evidence records. PatchCore is an
  anomaly detector/localizer, not a semantic defect classifier.
* MVTec RCA/path outputs are candidate/plausible explanations, not native MVTec
  factory root-cause labels.

## Assumptions (temporary)

* Defect Spectrum contains at least one MVTec-like image subtree that can be
  adapted to the existing `build_dataset_records.py --dataset mvtec` discovery
  format.
* The existing PatchCore checkpoint is compatible enough with the selected
  image category for a smoke run.

## Open Questions

* None blocking yet; inspect the local dataset and current runtime first.

## Requirements (evolving)

* Confirm whether PatchCore is already runnable from the current checkout.
* If runnable, produce records, adapter output, and a compact run summary under
  an ignored experiment directory.
* If blocked, record the exact failure, likely cause, and next step.
* Preserve evidence provenance and do not claim semantic defect classes are
  model-inferred.

## Acceptance Criteria (evolving)

* [x] Identify an input subset from `/Users/hhm/Downloads/Defect_Spectrum`.
* [x] Run PatchCore inference through the existing producer command.
* [x] Run generated records through the adapter pipeline.
* [x] Record command, artifact paths, and any blocker in this task.

## Definition of Done (team quality bar)

* Tests added/updated if code changes are required.
* Lint/typecheck considered if Python code changes are required.
* Docs/notes updated if behavior changes or the run is blocked.
* Rollout/rollback considered if risky.

## Out of Scope

* Training a new PatchCore model.
* Claiming verified MVTec root causes.
* Adding unsupported industrial causal KG edges.
* Building a new semantic defect classifier in this task.

## Technical Notes

* Relevant producer command: `scripts/build_dataset_records.py --dataset mvtec`.
* Relevant adapter command: `scripts/run_adapter_pipeline.py --dataset mvtec`.
* Relevant specs read: backend adapter guidelines, MVTec model presets, quality
  guidelines, and cross-layer thinking guide.

## 2026-05-12 Experiment Notes

Input data inspected:

* Defect Spectrum root: `/Users/hhm/Downloads/Defect_Spectrum`
* DS-MVTec image layout: `DS-MVTec/<object>/image/<defect>/*.png`
* DS-MVTec mask layout: `DS-MVTec/<object>/mask/<defect>/*_mask.png`
* The existing producer expects MVTec-like
  `input_root/<object>/test/<defect>/*.png`, so the smoke run used a symlinked
  capsule subset under `runs/patchcore_defect_spectrum/20260512_smoke/input_root`.

PatchCore availability:

* `resolve_mvtec_model_selection("patchcore")` resolves to
  `runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt`.
* `auto` currently resolves to PatchCore because EfficientAD is not present and
  PatchCore is available.
* Runtime imports exist for `anomalib`, `torch`, `torchvision`, `lightning`,
  `cv2`, and `PIL`.

Commands run:

```bash
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root runs/patchcore_defect_spectrum/20260512_smoke/input_root \
  --output-jsonl runs/patchcore_defect_spectrum/20260512_smoke/mvtec_patchcore_records.jsonl \
  --model-backend anomalib-engine \
  --checkpoint runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt \
  --device cpu \
  --max-cases 2 \
  --overwrite

uv run python scripts/run_adapter_pipeline.py \
  --input runs/patchcore_defect_spectrum/20260512_smoke/mvtec_patchcore_records.jsonl \
  --dataset mvtec \
  --output-dir runs/patchcore_defect_spectrum/20260512_smoke/adapter_pipeline \
  --top-k 5 \
  --overwrite
```

Produced artifacts:

* Producer records:
  `runs/patchcore_defect_spectrum/20260512_smoke/mvtec_patchcore_records.jsonl`
* Predicted heatmap/mask JSON:
  `runs/patchcore_defect_spectrum/20260512_smoke/mvtec_patchcore_records/`
* Adapter summary:
  `runs/patchcore_defect_spectrum/20260512_smoke/adapter_pipeline/adapter_pipeline_summary.json`
* Adapter table:
  `runs/patchcore_defect_spectrum/20260512_smoke/adapter_pipeline/adapter_pipeline_table.csv`

Observed result:

* Engineering chain is runnable: PatchCore inference, record generation,
  adapter conversion, and KGTracePipeline all completed.
* Two defect records were produced: one `crack`, one `scratch`.
* KG pipeline produced linked entities and plausible paths. For example, scratch
  linked to `ScratchDefect` and produced paths toward `MechanicalContact`,
  `HandlingDamage`, and `SurfaceWear`.

Quality warning:

* PatchCore predicted mask area was 100 percent for both defect images.
* Resized GT mask area was only about 0.15-0.17 percent.
* Predicted-mask IoU against resized GT was about 0.0015-0.0017.
* A `good` capsule sample was also scored as anomalous with `pred_score=1.0`
  and a full-image predicted mask.
* Raw Anomalib prediction fields include `pred_score=tensor([1.])`,
  `pred_label=tensor([True])`, `anomaly_map`, and `pred_mask`; this is not just a
  KGTraceVis field extraction mistake.
* Threshold sweeps over the raw anomaly map did not recover useful localization:
  the best quick IoU was about 0.005 for crack and 0.015 for scratch, with large
  predicted areas still far above the GT mask area.

Conclusion:

* PatchCore is "run through" at the software-integration level.
* Current PatchCore checkpoint plus current Anomalib Engine inference is not yet
  reliable enough for mask-derived MVTec evidence on Defect Spectrum. The next
  implementation step should calibrate or replace the predicted-mask generation,
  verify checkpoint/data-domain compatibility, and add a small regression command
  that checks good-vs-defect score separation and mask area sanity.

## 2026-05-12 Follow-up: Target-domain PatchCore Fit

User clarified that the top priority is not DS-MVTec layout support, but making
PatchCore produce normal outputs through the full chain.

Additional finding:

* The downloaded public capsule PatchCore checkpoint is runnable, but not usable
  for Defect Spectrum capsule evidence as-is: it marks `good`, `crack`, and
  `scratch` as anomalous with full-image masks.
* Fitting PatchCore on the target Defect Spectrum capsule `image/good` set and
  calibrating with same-object normal/abnormal validation restores a normal
  detection shape:
  * `good`: score around 0.34, `pred_label=False`, mask area 0.
  * `crack`: score around 0.83, `pred_label=True`, mask area about 0.004.
  * `scratch`: score around 0.86, `pred_label=True`, mask area about 0.010.
* The full producer -> adapter -> KGTracePipeline chain succeeds with this
  target-domain checkpoint. The remaining quality gap is localization accuracy:
  predicted masks are small and non-degenerate, but quick IoU checks against
  resized DS-MVTec GT masks are still weak and need a dedicated validation pass.

Implementation added:

* `scripts/fit_mvtec_patchcore.py`
  * Fits PatchCore on `object/image/good`.
  * Uses all defect labels by default for threshold calibration.
  * Can evaluate a selected subset with repeated `--eval-label`.
  * Runs `build_mvtec_records` and `run_adapter_pipeline`.
  * Writes `summary.json` with checkpoint, records, adapter artifacts, and sanity
    rows.

Verified command:

```bash
uv run python scripts/fit_mvtec_patchcore.py \
  --object-dir /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec/capsule \
  --output-root runs/patchcore_defect_spectrum/script_smoke_capsule_fullfit \
  --name ds_mvtec_capsule_script_fullfit \
  --eval-label crack \
  --eval-label scratch \
  --max-eval-per-label 1 \
  --device cpu \
  --overwrite
```

Verification:

* `uv run --extra dev ruff check scripts/fit_mvtec_patchcore.py`
* `uv run --extra dev pytest tests/test_record_producers.py -q`

## 2026-05-12 Follow-up: Broader Chain Runs

Capsule all-defect small evaluation:

```bash
uv run python scripts/fit_mvtec_patchcore.py \
  --object-dir /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec/capsule \
  --output-root runs/patchcore_defect_spectrum/capsule_eval_5_per_label \
  --name ds_mvtec_capsule_eval_5_per_label \
  --max-eval-per-label 5 \
  --device cpu \
  --overwrite
```

Capsule result:

* 29 records were generated and passed through the adapter/KG pipeline.
* Detection sanity: 25/25 defect samples predicted anomalous, 4/4 good samples
  predicted normal.
* Mask output is no longer degenerate/full-image. Predicted area ranges from 0
  to about 11.4 percent.
* Pixel localization remains uneven: defect-only mean IoU against DS-MVTec masks
  is about 0.132. `squeeze` and `poke` are usable for coarse localization, while
  the sampled `scratch` masks had IoU 0. This should be treated as an evidence
  quality limitation, not a chain blocker.
* Artifacts:
  * `runs/patchcore_defect_spectrum/capsule_eval_5_per_label/summary.json`
  * `runs/patchcore_defect_spectrum/capsule_eval_5_per_label/mask_iou_sanity_summary.json`
  * `runs/patchcore_defect_spectrum/capsule_eval_5_per_label/adapter_pipeline/`

Bottle cross-object smoke:

```bash
uv run python scripts/fit_mvtec_patchcore.py \
  --object-dir /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec/bottle \
  --output-root runs/patchcore_defect_spectrum/bottle_eval_3_per_label \
  --name ds_mvtec_bottle_eval_3_per_label \
  --max-eval-per-label 3 \
  --device cpu \
  --overwrite
```

Bottle result:

* 12 records were generated and passed through the adapter/KG pipeline.
* Detection sanity: 9/9 defect samples predicted anomalous, 3/3 good samples
  predicted normal.
* Pixel localization is substantially better than capsule in this small run:
  defect-only mean IoU is about 0.575; contamination mean IoU is about 0.687.
* This confirms that the target-domain PatchCore fit -> record producer ->
  adapter -> KG pipeline is not capsule-specific. The remaining work is quality
  calibration and throughput, especially avoiding per-image checkpoint reloads
  during producer inference.

Current conclusion:

* PatchCore is now runnable end-to-end on Defect Spectrum DS-MVTec with a
  target-domain fitted checkpoint.
* The previously bundled/public PatchCore checkpoint remains unsuitable for
  Defect Spectrum capsule, because it produced full-image masks and false
  positives on good samples.
* The correct v0 evidence stance is:
  * image-level anomaly score and label are reliable enough for pipeline smoke
    and KG evidence generation on the tested objects;
  * predicted masks are usable as coarse localization evidence, but should carry
    quality metadata and should not be over-interpreted as precise segmentation;
  * folder labels remain source annotations, not PatchCore-inferred semantic
    classes.

## 2026-05-12 Follow-up: Reproducible Batch Runner

Implementation added:

* `src/kgtracevis/experiments/mvtec_patchcore.py`
  * Extracts reusable DS-MVTec object discovery, eval-root construction,
    single-object PatchCore fit/eval orchestration, record sanity aggregation,
    optional mask IoU calculation, and batch JSON/CSV writing.
  * Keeps PatchCore outputs scoped as anomaly detection/localization evidence;
    DS-MVTec folder labels remain source annotations.
* `scripts/fit_mvtec_patchcore.py`
  * Now delegates to the reusable experiment helper while preserving the
    single-object CLI.
* `scripts/run_mvtec_patchcore_batch.py`
  * Iterates DS-MVTec object directories.
  * Supports repeated `--object`, `--max-objects`, `--max-eval-per-label`,
    `--device`, `--top-k`, and `--overwrite`.
  * Continues after per-object failures and writes object status rows.
  * Produces top-level `batch_summary.json` and `batch_summary.csv` with
    record count, good/defect detection counts, score range, mask area range,
    optional mean IoU, artifact paths, and error text.

Example batch command:

```bash
uv run python scripts/run_mvtec_patchcore_batch.py \
  --dataset-root /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec \
  --output-root runs/patchcore_defect_spectrum/batch_smoke_2_objects \
  --max-objects 2 \
  --max-eval-per-label 1 \
  --device cpu \
  --top-k 5 \
  --overwrite
```

Focused verification:

```bash
uv run --extra dev ruff check \
  scripts/fit_mvtec_patchcore.py \
  scripts/run_mvtec_patchcore_batch.py \
  src/kgtracevis/experiments/mvtec_patchcore.py \
  tests/test_mvtec_patchcore_experiment.py

uv run --extra dev pytest tests/test_mvtec_patchcore_experiment.py -q
```

Independent check fixes:

* Resolved source paths before symlink/copy construction so relative
  `object_dir` inputs do not create broken eval-root links.
* Fixed prediction label parsing so `abnormal` is treated as anomalous rather
  than matching the substring `normal`.
* Preserved batch continue-on-error semantics when an existing object
  `summary.json` is corrupt or unreadable.
* Added lightweight regression tests for these helper behaviors without running
  Anomalib training in unit tests.

Post-check real smoke:

```bash
uv run python scripts/run_mvtec_patchcore_batch.py \
  --dataset-root /Users/hhm/Downloads/Defect_Spectrum/DS-MVTec \
  --output-root runs/patchcore_defect_spectrum/batch_smoke_bottle_1_after_check \
  --object bottle \
  --max-eval-per-label 1 \
  --device cpu \
  --overwrite
```

Smoke result:

* `batch_summary.json` reported `success_count=1`, `failed_count=0`.
* Bottle produced 4 records: 3/3 defect samples predicted anomalous and 1/1
  good sample predicted normal.
* Mean IoU over the three defect masks was about 0.606.
* Adapter/KG output paths were written under
  `runs/patchcore_defect_spectrum/batch_smoke_bottle_1_after_check/bottle/`.

Additional verification reported by the independent check:

* `uv run --extra dev ruff check .`
* `uv run --extra dev mypy src tests scripts`
* `uv run --extra dev pytest -q` (`138 passed`)
* `uv run python scripts/run_examples.py`

Spec update:

* `.trellis/spec/backend/mvtec-model-presets.md` now documents the
  DS-MVTec target-domain PatchCore command signatures, output contracts,
  validation/error behavior, required tests, and the evidence boundary.
