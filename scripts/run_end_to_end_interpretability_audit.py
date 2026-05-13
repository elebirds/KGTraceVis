"""Run strict end-to-end interpretability audit artifacts."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from kgtracevis.kg_construction.end_to_end_interpretability_audit import (
    DEFAULT_MVTEC_RECORDS,
    DEFAULT_MVTEC_TABLE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WM811K_RECORDS,
    DEFAULT_WM811K_TABLES,
    write_end_to_end_interpretability_audit,
)


def parse_args() -> argparse.Namespace:
    """Parse strict audit arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate strict end-to-end producer-record -> Evidence adapter -> "
            "KGTracePipeline overlay audit artifacts."
        )
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
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Write strict audit artifacts and print compact paths."""
    args = parse_args()
    command = " ".join(shlex.quote(part) for part in sys.argv)
    output = write_end_to_end_interpretability_audit(
        output_dir=args.output_dir,
        mvtec_records_path=args.mvtec_records,
        mvtec_adapter_table_path=args.mvtec_table,
        wm811k_record_paths=args.wm811k_record or DEFAULT_WM811K_RECORDS,
        wm811k_adapter_table_paths=args.wm811k_table or DEFAULT_WM811K_TABLES,
        top_k=args.top_k,
        top_n=args.top_n,
        overwrite=args.overwrite,
        commands_run=[command],
    )
    print(
        json.dumps(
            {
                "summary_path": str(output.summary_path),
                "markdown_path": str(output.markdown_path),
                "candidate_kg_dir": str(output.candidate_kg_dir),
                "case_ranking_dir": str(output.case_ranking_dir),
                "strict_audit_passed": output.summary["strict_audit_passed"],
                "dataset_count": len(output.summary["datasets"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
