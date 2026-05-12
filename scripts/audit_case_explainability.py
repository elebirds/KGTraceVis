"""Audit case explainability for coverage-first KG hardening."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg_construction.case_kg_hardening import (
    audit_mvtec_cases,
    audit_wm811k_cases,
    write_case_audit_artifacts,
)

DEFAULT_MVTEC_RECORDS = Path("runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl")
DEFAULT_MVTEC_TABLE = Path(
    "runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_table.csv"
)
DEFAULT_WM811K_RECORDS = [
    Path("runs/wm811k_real_recognition_smoke/wm811k_records.jsonl"),
    Path("data/examples/records/wm811k_records.jsonl"),
]
DEFAULT_WM811K_TABLES = [
    Path("runs/wm811k_real_recognition_smoke/adapter_pipeline/adapter_pipeline_table.csv"),
    Path("runs/adapter_pipeline_suite_check/adapter_pipeline_wm811k/adapter_pipeline_table.csv"),
]
DEFAULT_OUTPUT_DIR = Path("runs/paper_case_kg_audit")


def parse_args() -> argparse.Namespace:
    """Parse case-audit arguments."""
    parser = argparse.ArgumentParser(
        description="Generate MVTec/WM811K explainability ranking artifacts."
    )
    parser.add_argument("--mvtec-records", type=Path, default=DEFAULT_MVTEC_RECORDS)
    parser.add_argument("--mvtec-table", type=Path, default=DEFAULT_MVTEC_TABLE)
    parser.add_argument(
        "--wm811k-record",
        action="append",
        type=Path,
        default=[],
        help="WM811K producer JSONL path. May be repeated.",
    )
    parser.add_argument(
        "--wm811k-table",
        action="append",
        type=Path,
        default=[],
        help="WM811K adapter table CSV path. May be repeated.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    """Write audit artifacts and print compact output paths."""
    args = parse_args()
    mvtec_rows = audit_mvtec_cases(args.mvtec_records, args.mvtec_table)
    wm811k_rows = audit_wm811k_cases(
        args.wm811k_record or DEFAULT_WM811K_RECORDS,
        args.wm811k_table or DEFAULT_WM811K_TABLES,
    )
    mvtec_paths = write_case_audit_artifacts(
        mvtec_rows,
        args.output_dir,
        prefix="mvtec",
        top_n=args.top_n,
    )
    wm811k_paths = write_case_audit_artifacts(
        wm811k_rows,
        args.output_dir,
        prefix="wm811k",
        top_n=args.top_n,
    )
    print(
        json.dumps(
            {
                "mvtec_case_count": len(mvtec_rows),
                "wm811k_case_count": len(wm811k_rows),
                "mvtec": mvtec_paths,
                "wm811k": wm811k_paths,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
