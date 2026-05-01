"""Run structured QA checks for source-constrained KG CSV files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS
from kgtracevis.kg_construction.qa import run_kg_qa


def main() -> None:
    """Run KG QA and optionally write a JSON report."""
    args = _parse_args()
    node_paths = [Path(path) for path in args.nodes]
    edge_paths = [Path(path) for path in args.edges]
    report = run_kg_qa(
        node_paths,
        edge_paths,
        reviewed_low_confidence_threshold=args.reviewed_low_confidence_threshold,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")

    summary = report.summary()
    print(
        "kg qa "
        f"nodes={summary['node_count']}, edges={summary['edge_count']}, "
        f"issues={summary['issue_count']}, warnings={summary['warning_count']}, "
        f"passed={summary['passed']}"
    )
    if args.output:
        print(f"kg qa output={args.output}")
    if report.issue_count:
        raise SystemExit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nodes",
        nargs="+",
        default=[str(path) for path in DEFAULT_NODE_PATHS],
        help="Node CSV path(s). Defaults to the development KG node paths.",
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        default=[str(path) for path in DEFAULT_EDGE_PATHS],
        help="Edge CSV path(s). Defaults to the development KG edge paths.",
    )
    parser.add_argument(
        "--reviewed-low-confidence-threshold",
        type=float,
        default=0.7,
        help="Warn when reviewed edges are below this confidence threshold.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional ignored-path JSON report, for example outputs/kg_qa_report.json.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
