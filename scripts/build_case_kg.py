"""Build coverage-first candidate KG artifacts for paper cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from kgtracevis.kg_construction.case_kg_hardening import write_candidate_kg_artifacts
from kgtracevis.schema.evidence_schema import DatasetName

DEFAULT_MVTEC_RECORDS = Path("runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl")
DEFAULT_MVTEC_TABLE = Path(
    "runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_table.csv"
)
DEFAULT_WM811K_RECORDS = [
    Path("runs/wm811k_real_recognition_smoke/wm811k_records.jsonl"),
    Path("data/examples/records/wm811k_records.jsonl"),
]
DEFAULT_OUTPUT_DIR = Path("runs/paper_case_kg")


def parse_args() -> argparse.Namespace:
    """Parse candidate-KG build arguments."""
    parser = argparse.ArgumentParser(
        description="Build candidate KG CSVs and before/after reasoning artifacts."
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
        "--before-after-input",
        action="append",
        default=[],
        help=(
            "Before/after input in label:dataset:path form, e.g. "
            "mvtec:mvtec:runs/.../records.jsonl. May be repeated."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Generate candidate KG artifacts and print compact output paths."""
    args = parse_args()
    wm811k_records = args.wm811k_record or DEFAULT_WM811K_RECORDS
    before_after_inputs = (
        [_parse_before_after_input(value) for value in args.before_after_input]
        if args.before_after_input
        else _default_before_after_inputs(args.mvtec_records, wm811k_records)
    )
    output = write_candidate_kg_artifacts(
        output_dir=args.output_dir,
        mvtec_records_path=args.mvtec_records,
        mvtec_adapter_table_path=args.mvtec_table,
        wm811k_record_paths=wm811k_records,
        before_after_inputs=before_after_inputs,
        top_k=args.top_k,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "nodes_path": str(output.nodes_path),
                "edges_path": str(output.edges_path),
                "summary_path": str(output.summary_path),
                "validation_path": str(output.validation_path),
                "review_queue_path": str(output.review_queue_path),
                "coverage_report_path": str(output.coverage_report_path),
                "before_after_path": str(output.before_after_path),
                "explanations_path": str(output.explanations_path),
                "node_count": output.node_count,
                "edge_count": output.edge_count,
                "validation_passed": output.validation_passed,
            },
            indent=2,
        )
    )


def _default_before_after_inputs(
    mvtec_records: Path,
    wm811k_records: list[Path],
) -> list[tuple[Path, DatasetName, str]]:
    inputs: list[tuple[Path, DatasetName, str]] = []
    if mvtec_records.exists():
        inputs.append((mvtec_records, "mvtec", "mvtec"))
    for index, path in enumerate(wm811k_records, start=1):
        if path.exists():
            inputs.append((path, "wafer", f"wm811k_{index}"))
    return inputs


def _parse_before_after_input(value: str) -> tuple[Path, DatasetName, str]:
    parts = value.split(":", 2)
    if len(parts) != 3:
        raise ValueError("--before-after-input must use label:dataset:path")
    label, dataset, path = parts
    if dataset not in {"mvtec", "tep", "wafer"}:
        raise ValueError("before/after dataset must be one of mvtec, tep, wafer")
    return (Path(path), cast(DatasetName, dataset), label)


if __name__ == "__main__":
    main()
