"""Build producer-output dataset records from local raw/subset data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.dataset_records import (
    MODEL_BACKENDS,
    DatasetRecordBuildConfig,
    build_dataset_records,
    build_mvtec_predictor,
    build_wm811k_classifier,
)

__all__ = [
    "build_dataset_records",
    "build_mvtec_predictor",
    "build_wm811k_classifier",
    "main",
    "parse_args",
]


def parse_args() -> argparse.Namespace:
    """Parse producer record build arguments."""
    parser = argparse.ArgumentParser(
        description="Build normalized producer-output records for adapter ingestion."
    )
    parser.add_argument("--dataset", required=True, choices=("mvtec", "wm811k", "wafer"))
    parser.add_argument("--input-root", type=Path, help="MVTec-like input directory root.")
    parser.add_argument("--input", type=Path, help="WM811K pandas-readable input table.")
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument(
        "--model-backend",
        required=True,
        choices=MODEL_BACKENDS,
        help=(
            "Real inference backend. MVTec supports anomalib-torch and "
            "anomalib-openvino. PatchCore Lightning checkpoints use anomalib-engine. "
            "Official Amazon PatchCore artifact directories use amazon-patchcore. "
            "WM811K supports sklearn and torch-resnet34."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help=(
            "Model checkpoint path. Required for all real backends; sklearn "
            "joblib/pickle files must be trusted local files."
        ),
    )
    parser.add_argument(
        "--model-source-repo",
        help=(
            "Optional public model source repo recorded in WM811K torch-resnet34 "
            "producer metadata, for example radai-agent/radai-wm811k-defect-detection."
        ),
    )
    parser.add_argument(
        "--model-source-file",
        help=(
            "Optional public model source filename recorded in WM811K torch-resnet34 "
            "producer metadata, for example best_radai_resnet.pt."
        ),
    )
    parser.add_argument(
        "--object-checkpoint-root",
        type=Path,
        help=(
            "Root containing official Amazon PatchCore object artifact directories "
            "such as mvtec_bottle and mvtec_capsule. Only valid with "
            "--model-backend amazon-patchcore."
        ),
    )
    parser.add_argument("--threshold", default=0.5, type=float)
    parser.add_argument(
        "--threshold-config",
        type=Path,
        help=(
            "Optional MVTec per-object threshold config JSON. Applies calibrated "
            "score/map thresholds when building producer records."
        ),
    )
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--max-per-label", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--device",
        help="Optional device passed to supported local model inferencers.",
    )
    parser.add_argument(
        "--include-good",
        action="store_true",
        help="Include MVTec good/normal samples in the produced record subset.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing JSONL output.")
    return parser.parse_args()


def main() -> None:
    """Build records and print a compact JSON summary."""
    args = parse_args()
    result = build_dataset_records(
        DatasetRecordBuildConfig(
            dataset=args.dataset,
            input_root=args.input_root,
            input=args.input,
            output_jsonl=args.output_jsonl,
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
            model_source_repo=args.model_source_repo,
            model_source_file=args.model_source_file,
            object_checkpoint_root=args.object_checkpoint_root,
            threshold=args.threshold,
            threshold_config=args.threshold_config,
            max_cases=args.max_cases,
            max_per_label=args.max_per_label,
            seed=args.seed,
            device=args.device,
            include_good=args.include_good,
            overwrite=args.overwrite,
        )
    )
    print(json.dumps(result.summary, indent=2))


if __name__ == "__main__":
    main()
