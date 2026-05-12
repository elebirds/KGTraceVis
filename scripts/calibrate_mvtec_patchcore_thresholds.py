"""Calibrate quick supervised thresholds for official Amazon PatchCore MVTec evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from kgtracevis.experiments.mvtec_patchcore import (
    IMAGE_SUFFIXES,
    discover_ds_mvtec_object_dirs,
    image_files,
    mask_for_image,
    symlink_or_copy,
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

    input_root, manifest = build_calibration_input(
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


def build_calibration_input(
    *,
    dataset_root: Path,
    output_root: Path,
    object_names: list[str] | None,
    max_objects: int | None,
    max_good: int,
    max_defect_per_label: int,
) -> tuple[Path, list[dict[str, Any]]]:
    """Create a small MVTec-like input tree for calibration."""
    if max_good < 1:
        raise ValueError("--max-good must be >= 1")
    if max_defect_per_label < 1:
        raise ValueError("--max-defect-per-label must be >= 1")
    if output_root.exists():
        shutil.rmtree(output_root)
    object_dirs = discover_ds_mvtec_object_dirs(
        dataset_root,
        object_names=object_names,
        max_objects=max_objects,
        normal_label="good",
    )
    input_root = output_root / "input_root"
    manifest: list[dict[str, Any]] = []
    for object_dir in object_dirs:
        image_root = object_dir / "image"
        mask_root = object_dir / "mask"
        for image_path in image_files(image_root / "good")[:max_good]:
            destination = input_root / object_dir.name / "test" / "good" / image_path.name
            symlink_or_copy(image_path, destination)
            manifest.append(
                {
                    "object": object_dir.name,
                    "label": "good",
                    "image_path": str(image_path),
                    "linked_path": str(destination),
                }
            )
        defect_dirs = sorted(
            path for path in image_root.iterdir() if path.is_dir() and path.name != "good"
        )
        for defect_dir in defect_dirs:
            for image_path in image_files(defect_dir)[:max_defect_per_label]:
                destination = (
                    input_root / object_dir.name / "test" / defect_dir.name / image_path.name
                )
                symlink_or_copy(image_path, destination)
                row = {
                    "object": object_dir.name,
                    "label": defect_dir.name,
                    "image_path": str(image_path),
                    "linked_path": str(destination),
                }
                mask_path = mask_for_image(mask_root / defect_dir.name, image_path)
                if mask_path is not None and mask_path.suffix.lower() in IMAGE_SUFFIXES:
                    mask_destination = (
                        input_root
                        / object_dir.name
                        / "ground_truth"
                        / defect_dir.name
                        / mask_path.name
                    )
                    symlink_or_copy(mask_path, mask_destination)
                    row["mask_path"] = str(mask_path)
                    row["linked_mask_path"] = str(mask_destination)
                manifest.append(row)
    manifest_path = output_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return input_root, manifest


if __name__ == "__main__":
    main()
