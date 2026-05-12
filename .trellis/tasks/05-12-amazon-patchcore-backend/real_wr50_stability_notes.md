# Official Amazon PatchCore Real WR50 Stability Notes

Date: 2026-05-12

## Setup

- Official repo clone: `artifacts/third_party/patchcore-inspection`
- Official artifact directory:
  `artifacts/third_party/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_bottle`
- WR50 pretrained weights:
  `~/.cache/torch/hub/checkpoints/wide_resnet50_2-95faca4d.pth`
- Weight SHA256:
  `95faca4d11227dddf8633dbb5ff6c8a9003c1aa5b8945c73834b8007b10950b8`
- Required macOS runtime environment for stable FAISS + PyTorch execution:
  `KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`

## Smoke Runs

Single-image real WR50 smoke:

- Run directory: `runs/amazon_patchcore_smoke_real_wr50`
- Result: producer record generated, heatmap/mask files generated, adapter
  pipeline summary/table generated.

Per-label 20-image smoke:

- Run directory: `runs/amazon_patchcore_stability_real_wr50`
- Attempted: 20
- Producer success: 20/20
- Adapter success: true

Full DS-MVTec bottle smoke:

- Run directory: `runs/amazon_patchcore_stability_real_wr50_all_bottle`
- Source: `/Users/hhm/Downloads/Defect_Spectrum/DS-MVTec/bottle/image`
- Attempted: 83
- Producer success: 83/83
- Adapter success: true
- Adapter case count: 83
- Total elapsed: 22.997s
- Mean elapsed per image: 0.276s

## Score Summary

All samples:

- Score range: 1.87 - 10.60
- Mean score: 6.12
- Median score: 6.87

By label:

- `good`: mean 2.30, range 1.87 - 3.94
- `broken_small`: mean 7.72, range 5.66 - 9.73
- `broken_large`: mean 7.90, range 6.20 - 10.04
- `contamination`: mean 6.39, range 3.83 - 10.60

## Stability Conclusion

The engineering chain is stable for the tested bottle object:

```text
official Amazon PatchCore artifact
-> AmazonPatchCoreBackend
-> producer records
-> Evidence adapter
-> KGTracePipeline summary/table
```

No producer or adapter failures occurred in the 83-image full bottle smoke.

## Evidence Quality Caveat

The raw PatchCore scores show useful anomaly-intensity separation: `good` samples
are substantially lower than most defect samples. However, the current fixed
mask threshold produces near-full-image masks:

- Mask area ratio range: 0.943 - 0.982
- This happens for both `good` and defect samples.

Therefore, current PatchCore records are suitable for score/heatmap evidence and
end-to-end KG plumbing, but mask-derived location/morphology should be treated
as low-trust until anomaly-map normalization or threshold calibration is added.
