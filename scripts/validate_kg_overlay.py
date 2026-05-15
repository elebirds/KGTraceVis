"""Validate candidate KG overlays against runtime RCA and import contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.kg_overlay_validation import (
    KGOverlayValidationConfig,
    run_kg_overlay_validation,
)


def parse_args() -> argparse.Namespace:
    """Parse candidate KG overlay validation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        help="Source-to-KG build directory containing nodes.csv and edges.csv.",
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
    parser.add_argument("--example-dir", default=Path("data/examples"), type=Path)
    parser.add_argument(
        "--output-path",
        type=Path,
        help=(
            "Optional validation report path. Defaults to "
            "<build-dir>/kg_overlay_validation_report.json when --build-dir is used."
        ),
    )
    parser.add_argument(
        "--overlay-only-import",
        action="store_true",
        help="Dry-run Neo4j import with only overlay CSVs instead of defaults plus overlay.",
    )
    parser.add_argument("--top-k", default=5, type=int)
    return parser.parse_args()


def main() -> None:
    """Run candidate KG overlay validation and print the report."""
    args = parse_args()
    result = run_kg_overlay_validation(
        KGOverlayValidationConfig(
            build_dir=args.build_dir,
            kg_node_paths=tuple(args.kg_node_path),
            kg_edge_paths=tuple(args.kg_edge_path),
            example_dir=args.example_dir,
            output_path=args.output_path,
            include_defaults_for_import=not args.overlay_only_import,
            top_k=args.top_k,
        )
    )
    print(json.dumps(result.report, indent=2))


if __name__ == "__main__":
    main()
