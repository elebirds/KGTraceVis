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
    parser.add_argument(
        "--tep-rca-provider",
        choices=("none", "native", "artifact"),
        default="none",
        help="Optional TEP RCA provider. Defaults to existing path projection behavior.",
    )
    parser.add_argument(
        "--tep-rca-artifact-dir",
        type=Path,
        help="TEP RCA artifact directory required when --tep-rca-provider=artifact.",
    )
    parser.add_argument(
        "--tep-rca-ranking-path",
        type=Path,
        help="Explicit TEP RCA ranking artifact path for artifact provider mode.",
    )
    parser.add_argument(
        "--tep-rca-contributions-path",
        type=Path,
        help="Optional TEP RCA contribution artifact path for artifact provider mode.",
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
        kg_node_paths=args.kg_node_path,
        kg_edge_paths=args.kg_edge_path,
        tep_rca_provider=args.tep_rca_provider,
        tep_rca_artifact_dir=args.tep_rca_artifact_dir,
        tep_rca_ranking_path=args.tep_rca_ranking_path,
        tep_rca_contributions_path=args.tep_rca_contributions_path,
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
