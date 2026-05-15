"""Validate candidate KG overlays against runtime RCA and import contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.kg.import_neo4j import dry_run_import
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline


@dataclass(frozen=True)
class KGOverlayValidationConfig:
    """Configuration for candidate KG overlay validation."""

    build_dir: Path | None = None
    kg_node_paths: tuple[Path, ...] = ()
    kg_edge_paths: tuple[Path, ...] = ()
    example_dir: Path = Path("data/examples")
    output_path: Path | None = None
    include_defaults_for_runtime: bool = True
    include_defaults_for_import: bool = True
    top_k: int = 5


@dataclass(frozen=True)
class KGOverlayValidationResult:
    """Structured candidate KG overlay validation result."""

    report: dict[str, Any]
    output_path: Path | None = None


def run_kg_overlay_validation(
    config: KGOverlayValidationConfig,
) -> KGOverlayValidationResult:
    """Validate candidate KG overlay CSVs against runtime and import contracts."""
    node_paths, edge_paths = resolve_overlay_paths(
        build_dir=config.build_dir,
        kg_node_paths=config.kg_node_paths,
        kg_edge_paths=config.kg_edge_paths,
    )
    runtime_node_paths = [*DEFAULT_NODE_PATHS, *node_paths]
    runtime_edge_paths = [*DEFAULT_EDGE_PATHS, *edge_paths]
    if not config.include_defaults_for_runtime:
        runtime_node_paths = list(node_paths)
        runtime_edge_paths = list(edge_paths)
    runtime_graph = KnowledgeGraph.from_paths(
        runtime_node_paths,
        runtime_edge_paths,
        skip_missing=True,
    )
    overlay_graph = KnowledgeGraph.from_paths(node_paths, edge_paths, skip_missing=True)
    overlay_edge_ids = {edge.edge_id for edge in overlay_graph.edges}
    overlay_kg_build_ids = {edge.kg_build_id for edge in overlay_graph.edges if edge.kg_build_id}
    pipeline = build_pipeline(graph=runtime_graph)
    example_reports = []
    for evidence_path in _example_files(config.example_dir):
        evidence = load_evidence_json(evidence_path)
        result = pipeline.analyze(evidence, top_k=config.top_k)
        example_reports.append(
            _example_report(
                evidence_path=evidence_path,
                case_id=evidence.case_id,
                dataset=evidence.dataset,
                result=result.model_dump(),
                overlay_edge_ids=overlay_edge_ids,
                overlay_kg_build_ids=overlay_kg_build_ids,
            )
        )
    if not example_reports:
        raise ValueError(f"no example JSON files found in {config.example_dir}")

    import_node_paths = [*DEFAULT_NODE_PATHS, *node_paths]
    import_edge_paths = [*DEFAULT_EDGE_PATHS, *edge_paths]
    if not config.include_defaults_for_import:
        import_node_paths = list(node_paths)
        import_edge_paths = list(edge_paths)
    import_graph = KnowledgeGraph.from_paths(
        import_node_paths,
        import_edge_paths,
        skip_missing=True,
    )
    import_summary = dry_run_import(import_graph)
    contribution_case_count = sum(
        1 for example in example_reports if example["overlay_contributed"]
    )
    contribution_edge_ids = _unique_values(
        edge_id
        for example in example_reports
        for edge_id in list(example.get("overlay_contribution_source_edge_ids") or [])
    )
    contribution_kg_build_ids = _unique_values(
        kg_build_id
        for example in example_reports
        for kg_build_id in list(example.get("overlay_contribution_kg_build_ids") or [])
    )
    contract_validated = import_summary.dry_run
    runtime_validated = len(example_reports) > 0
    overlay_contributed = contribution_case_count > 0
    report = {
        "artifact_type": "kg_overlay_validation_report_v1",
        "kg_backend": "explicit_seed_overlay",
        "build_dir": str(config.build_dir) if config.build_dir is not None else None,
        "kg_node_paths": [str(path) for path in node_paths],
        "kg_edge_paths": [str(path) for path in edge_paths],
        "runtime_graph": {
            "node_count": len(runtime_graph.nodes),
            "edge_count": len(runtime_graph.edges),
            "include_defaults": config.include_defaults_for_runtime,
        },
        "overlay_edge_count": len(overlay_graph.edges),
        "overlay_edge_ids": sorted(overlay_edge_ids),
        "overlay_kg_build_ids": sorted(overlay_kg_build_ids),
        "example_dir": str(config.example_dir),
        "example_count": len(example_reports),
        "examples": example_reports,
        "import_dry_run": {
            "node_count": import_summary.node_count,
            "edge_count": import_summary.edge_count,
            "dry_run": import_summary.dry_run,
            "include_defaults": config.include_defaults_for_import,
        },
        "contract_validated": contract_validated,
        "runtime_validated": runtime_validated,
        "overlay_contributed": overlay_contributed,
        "overlay_contribution_case_count": contribution_case_count,
        "overlay_contribution_source_edge_ids": contribution_edge_ids,
        "overlay_contribution_kg_build_ids": contribution_kg_build_ids,
        "missing_overlay_contribution_warning": (
            ""
            if overlay_contributed
            else (
                "Candidate overlay loaded and runtime examples executed, but no "
                "top-k RCA paths referenced overlay kg_build_ids or source_edge_ids."
            )
        ),
        "validated": contract_validated and runtime_validated and overlay_contributed,
    }
    output_path = config.output_path
    if output_path is None and config.build_dir is not None:
        output_path = config.build_dir / "kg_overlay_validation_report.json"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return KGOverlayValidationResult(report=report, output_path=output_path)


def resolve_overlay_paths(
    *,
    build_dir: Path | None,
    kg_node_paths: tuple[Path, ...],
    kg_edge_paths: tuple[Path, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Resolve candidate overlay node/edge paths from a build dir or explicit paths."""
    nodes = list(kg_node_paths)
    edges = list(kg_edge_paths)
    if build_dir is not None:
        build_nodes = build_dir / "nodes.csv"
        build_edges = build_dir / "edges.csv"
        if not build_nodes.is_file():
            raise ValueError(f"build directory is missing nodes.csv: {build_nodes}")
        if not build_edges.is_file():
            raise ValueError(f"build directory is missing edges.csv: {build_edges}")
        nodes.insert(0, build_nodes)
        edges.insert(0, build_edges)
    if not nodes:
        raise ValueError("at least one KG node overlay path or build directory is required")
    if not edges:
        raise ValueError("at least one KG edge overlay path or build directory is required")
    missing = [path for path in [*nodes, *edges] if not path.is_file()]
    if missing:
        raise ValueError(f"KG overlay path does not exist: {missing[0]}")
    return tuple(nodes), tuple(edges)


def _example_files(example_dir: Path) -> list[Path]:
    return sorted(example_dir.glob("*.json"))


def _example_report(
    *,
    evidence_path: Path,
    case_id: str,
    dataset: str,
    result: dict[str, Any],
    overlay_edge_ids: set[str],
    overlay_kg_build_ids: set[str],
) -> dict[str, Any]:
    paths = list(result.get("top_k_paths") or [])
    ranked_root_causes = list(result.get("ranked_root_causes") or [])
    path_kg_build_ids = _unique_values(
        kg_build_id
        for path in paths
        for kg_build_id in list(path.get("kg_build_ids") or [])
    )
    path_source_edge_ids = _unique_values(
        edge_id
        for path in paths
        for edge_id in list(path.get("source_edge_ids") or [])
    )
    contribution_kg_build_ids = sorted(set(path_kg_build_ids) & overlay_kg_build_ids)
    contribution_source_edge_ids = sorted(set(path_source_edge_ids) & overlay_edge_ids)
    overlay_contributed = bool(contribution_kg_build_ids or contribution_source_edge_ids)
    return {
        "path": str(evidence_path),
        "case_id": case_id,
        "dataset": dataset,
        "linked_count": len(result.get("linked_entities") or []),
        "consistency_score": result.get("consistency_score"),
        "top_k_path_count": len(paths),
        "ranked_root_cause_count": len(ranked_root_causes),
        "kg_build_ids": path_kg_build_ids,
        "path_strengths": [
            path.get("path_strength")
            for path in paths
            if path.get("path_strength") is not None
        ],
        "rca_scores": [
            path.get("rca_score") for path in paths if path.get("rca_score") is not None
        ],
        "source_edge_ids": path_source_edge_ids,
        "overlay_contributed": overlay_contributed,
        "overlay_contribution_kg_build_ids": contribution_kg_build_ids,
        "overlay_contribution_source_edge_ids": contribution_source_edge_ids,
        "top_path_id": str(paths[0].get("path_id") or "") if paths else "",
        "top_target_entity_id": (
            str(paths[0].get("target_entity_id") or "") if paths else ""
        ),
    }


def _unique_values(values: Any) -> list[str]:
    unique = {str(value) for value in values if str(value)}
    return sorted(unique)
