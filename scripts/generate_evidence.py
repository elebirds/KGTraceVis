"""Generate unified evidence JSON from batch record files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from kgtracevis.adapters import (
    evidence_from_records,
    load_records,
    summarize_evidence,
    write_evidence_files,
    write_evidence_jsonl,
)
from kgtracevis.schema.evidence_schema import DatasetName


def parse_args() -> argparse.Namespace:
    """Parse batch evidence generation arguments."""
    parser = argparse.ArgumentParser(
        description="Generate unified KGTraceVis evidence JSON from JSON, JSONL, or CSV records."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input .json, .jsonl, or .csv file.",
    )
    parser.add_argument(
        "--dataset",
        choices=("mvtec", "tep", "wafer"),
        help=(
            "Dataset adapter to use for all records. "
            "If omitted, each record must include dataset."
        ),
    )
    parser.add_argument("--output-dir", type=Path, help="Directory for one JSON file per case.")
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        help="Path for one JSONL file with all evidence.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    args = parser.parse_args()
    if args.output_dir is None and args.output_jsonl is None:
        parser.error("at least one of --output-dir or --output-jsonl is required")
    return args


def main() -> None:
    """Generate evidence files and print a compact summary."""
    args = parse_args()
    dataset = cast(DatasetName | None, args.dataset)
    records = load_records(args.input)
    evidence_items = evidence_from_records(records, dataset=dataset)
    if args.output_jsonl is not None:
        _ensure_cli_destination_available(args.output_jsonl, overwrite=args.overwrite)

    output_counts: dict[str, int | str] = {}
    if args.output_dir is not None:
        written_files = write_evidence_files(
            evidence_items, args.output_dir, overwrite=args.overwrite
        )
        output_counts["output_dir"] = str(args.output_dir)
        output_counts["output_dir_count"] = len(written_files)
    if args.output_jsonl is not None:
        jsonl_path = write_evidence_jsonl(
            evidence_items, args.output_jsonl, overwrite=args.overwrite
        )
        output_counts["output_jsonl"] = str(jsonl_path)
        output_counts["output_jsonl_count"] = len(evidence_items)

    summary = summarize_evidence(evidence_items).model_dump()
    summary["outputs"] = output_counts
    print(json.dumps(summary, indent=2))


def _ensure_cli_destination_available(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


if __name__ == "__main__":
    main()
