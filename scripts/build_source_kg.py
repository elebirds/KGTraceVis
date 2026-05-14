"""Build source-to-KG candidate CSV artifacts from registered extractor inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg_construction import (
    ExtractorRegistry,
    KGConstructionSource,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    run_kg_construction,
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

    output_dir = Path(args.output_dir)
    _ensure_output_dir(output_dir, overwrite=bool(args.overwrite))
    registry = ExtractorRegistry([TepSemanticLiftExtractor(), TepVariableMappingExtractor()])
    result = run_kg_construction(sources, registry=registry)
    nodes_path, edges_path = result.export_csv(output_dir)
    summary_path = output_dir / "kg_construction_summary.json"
    manifest_path = output_dir / "kg_construction_manifest.json"
    summary = {
        **result.summary,
        "output": {
            "nodes": str(nodes_path),
            "edges": str(edges_path),
            "summary": str(summary_path),
            "manifest": str(manifest_path),
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    result.write_manifest(
        manifest_path,
        artifact_paths={
            "nodes": nodes_path,
            "edges": edges_path,
            "summary": summary_path,
            "manifest": manifest_path,
        },
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


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


def _ensure_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    outputs = [
        output_dir / "nodes.csv",
        output_dir / "edges.csv",
        output_dir / "kg_construction_summary.json",
        output_dir / "kg_construction_manifest.json",
    ]
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        paths = ", ".join(str(path) for path in existing)
        raise SystemExit(f"Output files already exist; pass --overwrite to replace: {paths}")
    output_dir.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
