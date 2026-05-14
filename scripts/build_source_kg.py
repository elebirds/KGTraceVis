"""Build source-to-KG candidate CSV artifacts from registered extractor inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg_construction import (
    KGConstructionSource,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)


def parse_args() -> argparse.Namespace:
    """Parse source-to-KG build arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/source_kg_build"),
        help="Directory for candidate nodes/edges and summary artifacts.",
    )
    parser.add_argument(
        "--tep-semantic-lift-dir",
        type=Path,
        help=(
            "Directory containing semantic_lift_nodes.jsonl and "
            "semantic_lift_edges.jsonl from TEP_KG."
        ),
    )
    parser.add_argument(
        "--tep-semantic-nodes",
        type=Path,
        help="Explicit TEP_KG semantic_lift_nodes.jsonl path.",
    )
    parser.add_argument(
        "--tep-semantic-edges",
        type=Path,
        help="Explicit TEP_KG semantic_lift_edges.jsonl path.",
    )
    parser.add_argument(
        "--tep-variable-mapping",
        type=Path,
        help="TEP_KG tep_variable_mapping CSV/JSON/JSONL path.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Build candidate KG rows from source extractor inputs."""
    args = parse_args()
    sources = _build_sources(args)
    if not sources:
        raise SystemExit(
            "No source inputs provided. Pass --tep-semantic-lift-dir, "
            "--tep-semantic-nodes/--tep-semantic-edges, or --tep-variable-mapping."
        )

    try:
        result = run_source_kg_construction_workflow(
            SourceKGConstructionWorkflowConfig(
                output_dir=Path(args.output_dir),
                sources=tuple(sources),
                overwrite=bool(args.overwrite),
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result.summary, indent=2, sort_keys=True))


def _build_sources(args: argparse.Namespace) -> list[KGConstructionSource]:
    sources: list[KGConstructionSource] = []
    if args.tep_semantic_lift_dir is not None:
        sources.append(
            KGConstructionSource(
                source_id="tep_semantic_lift",
                source_type="tep_semantic_lift",
                scenario="tep",
                path=args.tep_semantic_lift_dir,
            )
        )
    if args.tep_semantic_nodes is not None or args.tep_semantic_edges is not None:
        if args.tep_semantic_nodes is None or args.tep_semantic_edges is None:
            raise SystemExit(
                "--tep-semantic-nodes and --tep-semantic-edges must be provided together"
            )
        sources.append(
            KGConstructionSource(
                source_id="tep_semantic_lift",
                source_type="tep_semantic_lift",
                scenario="tep",
                metadata={
                    "nodes_path": args.tep_semantic_nodes,
                    "edges_path": args.tep_semantic_edges,
                },
            )
        )
    if args.tep_variable_mapping is not None:
        sources.append(
            KGConstructionSource(
                source_id="tep_variable_mapping",
                source_type="tep_variable_mapping",
                scenario="tep",
                path=args.tep_variable_mapping,
            )
        )
    return sources


if __name__ == "__main__":
    main()
