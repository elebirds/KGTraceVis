"""Fit a target-domain PatchCore checkpoint and run the MVTec evidence path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.experiments.mvtec_patchcore import (
    PatchCoreObjectRunConfig,
    run_patchcore_object,
)


def parse_args() -> argparse.Namespace:
    """Parse PatchCore fit/evaluate options."""
    parser = argparse.ArgumentParser(
        description=(
            "Fit PatchCore on target-domain MVTec/DS-MVTec good images, then run "
            "producer records and KGTracePipeline on a small evaluation subset."
        )
    )
    parser.add_argument(
        "--object-dir",
        required=True,
        type=Path,
        help="Object directory containing image/good, image/<defect>, and mask/<defect>.",
    )
    parser.add_argument(
        "--output-root",
        default=Path("runs/patchcore_defect_spectrum/fit_patchcore"),
        type=Path,
    )
    parser.add_argument("--name", help="Anomalib dataset/run name. Defaults to object dir name.")
    parser.add_argument("--normal-label", default="good")
    parser.add_argument(
        "--eval-label",
        action="append",
        help="Defect label to evaluate. Repeat for multiple labels. Defaults to all defects.",
    )
    parser.add_argument(
        "--fit-label",
        action="append",
        help="Defect label to include while fitting thresholds. Defaults to all defects.",
    )
    parser.add_argument("--max-eval-per-label", default=1, type=int)
    parser.add_argument("--top-k", default=5, type=int)
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "gpu", "auto"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Fit PatchCore, run the producer/adapter pipeline, and print a summary."""
    args = parse_args()
    summary = run_patchcore_object(
        PatchCoreObjectRunConfig(
            object_dir=args.object_dir,
            output_root=args.output_root,
            name=args.name,
            normal_label=args.normal_label,
            fit_labels=args.fit_label,
            eval_labels=args.eval_label,
            max_eval_per_label=args.max_eval_per_label,
            top_k=args.top_k,
            device=args.device,
            overwrite=args.overwrite,
        )
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
