"""Run calibrated Amazon PatchCore MVTec records through KGTracePipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.experiments.mvtec_calibrated_pipeline import (
    MVTecCalibratedPipelineConfig,
    run_mvtec_calibrated_pipeline,
)


def parse_args() -> argparse.Namespace:
    """Parse calibrated pipeline CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build calibrated official Amazon PatchCore MVTec producer records, "
            "then run Evidence adapters and KGTracePipeline."
        )
    )
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument(
        "--threshold-config",
        default=Path("configs/mvtec_patchcore_thresholds.json"),
        type=Path,
    )
    parser.add_argument(
        "--output-root",
        default=Path("runs/mvtec_calibrated_pipeline"),
        type=Path,
    )
    parser.add_argument("--object", dest="objects", action="append")
    parser.add_argument("--max-objects", type=int)
    parser.add_argument("--max-good", default=1, type=int)
    parser.add_argument("--max-defect-per-label", default=1, type=int)
    parser.add_argument("--top-k", default=5, type=int)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the calibrated MVTec pipeline and print compact output paths."""
    args = parse_args()
    output = run_mvtec_calibrated_pipeline(
        MVTecCalibratedPipelineConfig(
            dataset_root=args.dataset_root,
            artifact_root=args.artifact_root,
            threshold_config=args.threshold_config,
            output_root=args.output_root,
            object_names=args.objects,
            max_objects=args.max_objects,
            max_good=args.max_good,
            max_defect_per_label=args.max_defect_per_label,
            top_k=args.top_k,
            device=args.device,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "summary_path": str(output.summary_path),
                "records_path": str(output.records_path),
                "adapter_summary": str(output.adapter_summary_path),
                "adapter_table": str(output.adapter_table_path),
                "record_count": output.summary["record_count"],
                "adapter_case_count": output.summary["adapter_case_count"],
                "object_count": output.summary["object_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
