"""Validate example evidence files and run the minimal pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.workflows.root_cause_provider_selection import (
    RootCauseProviderSelectionConfig,
    build_pipeline,
    normalize_root_cause_provider_selection,
)


def iter_example_files(example_dir: Path) -> list[Path]:
    """Return sorted example JSON files."""
    return sorted(example_dir.glob("*.json"))


def parse_args() -> argparse.Namespace:
    """Parse example validation arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--example-dir", default="data/examples")
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


def pipeline_from_kg_paths(
    *,
    kg_node_paths: list[Path],
    kg_edge_paths: list[Path],
    root_cause_provider_config: RootCauseProviderSelectionConfig | None = None,
) -> tuple[KGTracePipeline, str]:
    """Build the runtime pipeline, optionally with explicit KG CSV overlays."""
    if not kg_node_paths and not kg_edge_paths:
        return (
            build_pipeline(root_cause_provider_config=root_cause_provider_config),
            "neo4j",
        )
    graph = KnowledgeGraph.from_paths(
        [*DEFAULT_NODE_PATHS, *kg_node_paths],
        [*DEFAULT_EDGE_PATHS, *kg_edge_paths],
        skip_missing=True,
    )
    return (
        build_pipeline(
            graph=graph,
            root_cause_provider_config=root_cause_provider_config,
        ),
        "explicit_seed_overlay",
    )


def main() -> None:
    """Validate all example JSON files in a directory."""
    args = parse_args()

    example_dir = Path(args.example_dir)
    provider_config = RootCauseProviderSelectionConfig(
        tep_rca_provider=normalize_root_cause_provider_selection(args.tep_rca_provider),
        tep_rca_artifact_dir=args.tep_rca_artifact_dir,
        tep_rca_ranking_path=args.tep_rca_ranking_path,
        tep_rca_contributions_path=args.tep_rca_contributions_path,
    )
    pipeline, kg_backend = pipeline_from_kg_paths(
        kg_node_paths=args.kg_node_path,
        kg_edge_paths=args.kg_edge_path,
        root_cause_provider_config=provider_config,
    )
    results = []

    for path in iter_example_files(example_dir):
        evidence = load_evidence_json(path)
        result = pipeline.analyze(evidence)
        results.append(result.model_dump())
        print(
            "analyzed "
            f"{path}: case_id={evidence.case_id}, "
            f"linked={len(result.linked_entities)}, "
            f"consistency={result.consistency_score}, "
            f"paths={len(result.top_k_paths)}"
        )

    if not results:
        raise SystemExit(f"no example JSON files found in {example_dir}")

    payload = {"validated": len(results), "kg_backend": kg_backend}
    if provider_config.tep_rca_provider != "none":
        payload["root_cause_provider"] = provider_config.tep_rca_provider
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
