"""Calibrate quick supervised thresholds for official Amazon PatchCore MVTec evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from kgtracevis.experiments.mvtec_patchcore import (
    build_ds_mvtec_subset_input,
)
from kgtracevis.producers import AMAZON_PATCHCORE_BACKEND, AmazonPatchCoreObjectRouter
from kgtracevis.producers.common import write_jsonl_records
from kgtracevis.producers.mvtec_calibration import (
    calibrate_thresholds_from_records,
    write_threshold_config,
    write_threshold_csv,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records


def parse_args() -> argparse.Namespace:
    """Parse quick calibration arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run official Amazon PatchCore on a bounded DS-MVTec subset and write "
            "per-object supervised score/map thresholds for usable KGTraceVis evidence."
        )
    )
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument(
        "--output-root",
        default=Path("runs/mvtec_patchcore_quick_calibration"),
        type=Path,
    )
    parser.add_argument(
        "--output-config",
        default=Path("configs/mvtec_patchcore_thresholds.json"),
        type=Path,
    )
    parser.add_argument(
        "--output-csv",
        default=Path("configs/mvtec_patchcore_thresholds.csv"),
        type=Path,
    )
    parser.add_argument("--object", dest="objects", action="append")
    parser.add_argument("--max-objects", type=int)
    parser.add_argument("--max-good", default=5, type=int)
    parser.add_argument("--max-defect-per-label", default=3, type=int)
    parser.add_argument("--min-area-ratio", default=0.001, type=float)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run quick calibration and print output paths."""
    args = parse_args()
    if args.output_root.exists() and args.overwrite:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    input_root, manifest = build_ds_mvtec_subset_input(
        dataset_root=args.dataset_root,
        output_root=args.output_root / "input",
        object_names=args.objects,
        max_objects=args.max_objects,
        max_good=args.max_good,
        max_defect_per_label=args.max_defect_per_label,
    )
    predictor = AmazonPatchCoreObjectRouter(checkpoint_root=args.artifact_root, device=args.device)
    records = build_mvtec_records(
        input_root,
        predictor,
        output_dir=args.output_root / "records",
        model_backend=AMAZON_PATCHCORE_BACKEND,
        checkpoint=args.artifact_root,
        include_good=True,
    )
    records_path = write_jsonl_records(
        records,
        args.output_root / "calibration_records.jsonl",
        overwrite=True,
    )
    thresholds = calibrate_thresholds_from_records(
        records,
        min_area_ratio=args.min_area_ratio,
    )
    config_path = write_threshold_config(thresholds, args.output_config)
    csv_path = write_threshold_csv(thresholds, args.output_csv)
    summary = {
        "artifact_type": "mvtec_patchcore_quick_calibration_run_v0",
        "dataset_root": str(args.dataset_root),
        "artifact_root": str(args.artifact_root),
        "input_root": str(input_root),
        "records_path": str(records_path),
        "output_config": str(config_path),
        "output_csv": str(csv_path),
        "record_count": len(records),
        "object_count": len(thresholds),
        "manifest": manifest,
        "thresholds": [threshold.__dict__ for threshold in thresholds],
        "claim_boundary": (
            "Thresholds are supervised quick-calibration artifacts for stable "
            "KGTraceVis evidence, not unsupervised MVTec benchmark results."
        ),
    }
    summary_path = args.output_root / "calibration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "summary_path": str(summary_path),
                "records_path": str(records_path),
                "output_config": str(config_path),
                "output_csv": str(csv_path),
                "record_count": len(records),
                "object_count": len(thresholds),
            },
            indent=2,
        )
    )

if __name__ == "__main__":
    main()
