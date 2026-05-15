"""Build native-label pattern-stratified WM811K producer records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.paper_case_studies import (
    WM811KStratifiedBuildConfig,
    build_wm811k_stratified_records,
)


def parse_args() -> argparse.Namespace:
    """Parse WM811K stratified record build arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a bounded WM811K pattern-stratified record set from native "
            "labels for case-study coverage and traceability checks."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="WM811K pandas-readable table.")
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument(
        "--records-per-pattern",
        default=1,
        type=int,
        help="Maximum native-label records to sample per supported WM811K pattern.",
    )
    parser.add_argument("--seed", default=0, type=int)
    parser.add_argument(
        "--wafer-map-inline-limit",
        default=400,
        type=int,
        help="Maximum wafer-map cell count to inline in each record.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing outputs.")
    return parser.parse_args()


def main() -> None:
    """Run the reusable stratified build workflow."""
    args = parse_args()
    output = build_wm811k_stratified_records(
        WM811KStratifiedBuildConfig(
            input_path=args.input,
            output_jsonl=args.output_jsonl,
            records_per_pattern=args.records_per_pattern,
            seed=args.seed,
            wafer_map_inline_limit=args.wafer_map_inline_limit,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "records": str(output.output_path),
                "summary": str(output.summary_path),
                "record_count": output.summary["record_count"],
                "observed_patterns": output.summary["observed_patterns"],
                "missing_patterns": output.summary["missing_patterns"],
                "claim_boundary": output.summary["claim_boundary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
