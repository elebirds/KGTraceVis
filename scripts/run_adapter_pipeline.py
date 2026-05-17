"""Run producer-output records through adapters and KGTracePipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.schema.evidence_schema import DatasetName


def parse_args() -> argparse.Namespace:
    """Parse adapter-to-pipeline orchestration arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run JSON/JSONL/CSV producer-output records through Evidence adapters "
            "and KGTracePipeline."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input .json, .jsonl, or .csv record file.",
    )
    parser.add_argument(
        "--dataset",
        choices=("mvtec", "tep", "wafer"),
        help="Optional dataset adapter override for all records.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for generated evidence files and summary JSON.",
    )
    parser.add_argument(
        "--top-k",
        default=5,
        type=int,
        help="Number of ranked candidate/plausible explanation paths per case.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing outputs.")
    parser.add_argument(
        "--reasoning-profile",
        default=None,
        type=str,
        help="Optional registered reasoning profile ID for explicit RCA selection.",
    )
    parser.add_argument(
        "--kg-node-path",
        action="append",
        default=[],
        type=Path,
        help="Additional KG node CSV overlay path. May be passed multiple times.",
    )
    parser.add_argument(
        "--kg-edge-path",
        action="append",
        default=[],
        type=Path,
        help="Additional KG edge CSV overlay path. May be passed multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the adapter-to-pipeline helper and print a compact JSON result."""
    args = parse_args()
    dataset = cast(DatasetName | None, args.dataset)
    output = run_adapter_pipeline(
        args.input,
        args.output_dir,
        dataset=dataset,
        top_k=args.top_k,
        overwrite=args.overwrite,
        reasoning_profile_id=args.reasoning_profile,
        kg_node_paths=args.kg_node_path,
        kg_edge_paths=args.kg_edge_path,
    )
    print(
        json.dumps(
            {
                "summary_path": str(output.summary_path),
                "table_path": str(output.table_path),
                "evidence_count": len(output.evidence_paths),
                "case_count": output.summary["case_count"],
                "explanation_scope": output.summary["explanation_scope"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
