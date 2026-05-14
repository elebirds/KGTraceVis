"""Import KG seed CSV files into the Neo4j runtime backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.kg.import_neo4j import (
    Neo4jImportError,
    dry_run_import,
    import_knowledge_graph_with_config,
    resolve_neo4j_config,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nodes",
        action="append",
        dest="node_paths",
        help="Node CSV path. Repeat to import multiple node layers.",
    )
    parser.add_argument(
        "--edges",
        action="append",
        dest="edge_paths",
        help="Edge CSV path. Repeat to import multiple edge layers.",
    )
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help=(
            "When custom --nodes/--edges are provided, append them to the "
            "project default KG layers instead of replacing the defaults."
        ),
    )
    parser.add_argument("--config", default="configs/neo4j.example.yaml")
    parser.add_argument("--uri")
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and validate KG rows, then print counts without connecting to Neo4j.",
    )
    return parser.parse_args()


def load_graph(
    node_paths: list[str] | None,
    edge_paths: list[str] | None,
    *,
    include_defaults: bool = False,
) -> KnowledgeGraph:
    """Load validated KG rows from requested paths or project defaults."""
    custom_nodes = [Path(path) for path in node_paths or []]
    custom_edges = [Path(path) for path in edge_paths or []]
    has_custom_paths = bool(custom_nodes or custom_edges)
    if include_defaults or not has_custom_paths:
        nodes = [*DEFAULT_NODE_PATHS, *custom_nodes]
    else:
        nodes = custom_nodes
    if include_defaults or not has_custom_paths:
        edges = [*DEFAULT_EDGE_PATHS, *custom_edges]
    else:
        edges = custom_edges
    return KnowledgeGraph.from_paths(nodes, edges, skip_missing=True)


def main() -> None:
    """Import the configured KG into Neo4j, or perform a dry run."""
    args = parse_args()
    graph = load_graph(
        args.node_paths,
        args.edge_paths,
        include_defaults=args.include_defaults,
    )

    if args.dry_run:
        summary = dry_run_import(graph)
    else:
        try:
            config = resolve_neo4j_config(
                uri=args.uri,
                user=args.user,
                password=args.password,
                database=args.database,
                config_path=args.config,
            )
            summary = import_knowledge_graph_with_config(graph, config)
        except (Neo4jImportError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc

    print(json.dumps(summary.__dict__, indent=2))


if __name__ == "__main__":
    main()
