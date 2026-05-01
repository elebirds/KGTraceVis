"""Validate and summarize v0 KG CSV files from curated sources."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.kg_construction.export_kg_csv import export_kg_csv, validate_kg_csv_contract
from kgtracevis.kg_construction.source_loader import load_source_registry


def summarize_graph(graph: KnowledgeGraph, source_count: int) -> dict[str, object]:
    """Return a compact summary for a loaded KG."""
    node_scenarios = Counter(node.scenario for node in graph.nodes.values())
    edge_scenarios = Counter(edge.scenario for edge in graph.edges)
    review_statuses = Counter(edge.review_status for edge in graph.edges)
    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "sources": source_count,
        "node_scenarios": dict(sorted(node_scenarios.items())),
        "edge_scenarios": dict(sorted(edge_scenarios.items())),
        "review_statuses": dict(sorted(review_statuses.items())),
    }


def main() -> None:
    """Validate curated KG files and optionally export a normalized copy."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nodes",
        nargs="+",
        default=[str(path) for path in DEFAULT_NODE_PATHS],
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        default=[str(path) for path in DEFAULT_EDGE_PATHS],
    )
    parser.add_argument("--source-registry", default="data/kg/source_registry.csv")
    parser.add_argument(
        "--output-dir",
        help="Optional directory for normalized nodes.csv and edges.csv exports.",
    )
    args = parser.parse_args()

    source_records = load_source_registry(args.source_registry)
    graph = KnowledgeGraph.from_paths(args.nodes, args.edges)
    validate_kg_csv_contract(graph.nodes.values(), graph.edges)
    summary = summarize_graph(graph, source_count=len(source_records))

    if args.output_dir:
        output_dir = Path(args.output_dir)
        export_kg_csv(
            graph.nodes.values(),
            graph.edges,
            nodes_path=output_dir / "nodes.csv",
            edges_path=output_dir / "edges.csv",
        )
        summary["exported_to"] = str(output_dir)

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
