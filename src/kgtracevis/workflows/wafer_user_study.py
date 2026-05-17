"""Prepare wafer user-study assets for RootLens and backend runtime testing."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg.import_neo4j import ImportSummary, import_knowledge_graph_with_config, resolve_neo4j_config
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.service.runs import DEFAULT_RUNS_DIR, create_run_from_upload
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline

DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH = Path("data/examples/wafer_user_study_nearfull.json")
DEFAULT_WAFER_USER_STUDY_BASELINE_PATH = Path(
    "data/references/wafer_user_study_nearfull_baseline.md"
)
DEFAULT_WAFER_USER_STUDY_GRAPH_DIR = Path("runs/source_kg_build/wafer_user_study")
DEFAULT_WAFER_USER_STUDY_MANIFEST_PATH = Path("artifacts/wafer_user_study/manifest.json")
USER_STUDY_GRAPH_ARTIFACT_TYPE = "wafer_user_study_graph_v1"
GraphScope = Literal["full_runtime", "focused_anomaly"]


@dataclass(frozen=True)
class WaferUserStudyConfig:
    """Configuration for preparing wafer user-study assets."""

    evidence_path: Path = DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH
    baseline_path: Path = DEFAULT_WAFER_USER_STUDY_BASELINE_PATH
    graph_output_dir: Path = DEFAULT_WAFER_USER_STUDY_GRAPH_DIR
    manifest_path: Path = DEFAULT_WAFER_USER_STUDY_MANIFEST_PATH
    run_artifact_root: Path = DEFAULT_RUNS_DIR
    top_k: int = 5
    overwrite: bool = False
    create_run: bool = True
    import_runtime_kg: bool = True
    reasoning_profile_id: str | None = None
    graph_scope: GraphScope = "full_runtime"
    graph_hops: int = 2


@dataclass(frozen=True)
class WaferUserStudyResult:
    """Prepared user-study asset locations and summaries."""

    evidence_path: Path
    baseline_path: Path
    graph_output_dir: Path
    manifest_path: Path
    run_id: str | None
    graph_summary: dict[str, Any]
    runtime_kg_import: dict[str, Any] | None


def prepare_wafer_user_study(
    config: WaferUserStudyConfig,
    *,
    pipeline: KGTracePipeline | None = None,
) -> WaferUserStudyResult:
    """Prepare wafer user-study assets and optionally persist a test run."""
    evidence_path = config.evidence_path.expanduser()
    baseline_path = config.baseline_path.expanduser()
    graph_output_dir = config.graph_output_dir.expanduser()
    manifest_path = config.manifest_path.expanduser()
    run_artifact_root = config.run_artifact_root.expanduser()

    evidence = _load_wafer_user_study_evidence(evidence_path)
    _require_existing_file(baseline_path, label="baseline file")

    graph = KnowledgeGraph.from_paths(DEFAULT_NODE_PATHS, DEFAULT_EDGE_PATHS, skip_missing=True)
    graph_summary = materialize_wafer_user_study_graph(
        graph,
        evidence=evidence,
        output_dir=graph_output_dir,
        overwrite=config.overwrite,
        graph_scope=config.graph_scope,
        graph_hops=config.graph_hops,
    )

    runtime_kg_import = None
    if config.import_runtime_kg:
        runtime_kg_import = _runtime_kg_import_payload(graph)

    run_id = None
    if config.create_run:
        active_pipeline = pipeline or build_pipeline(
            graph=graph,
            reasoning_profile_id=config.reasoning_profile_id,
        )
        detail = create_run_from_upload(
            evidence_path.name,
            evidence_path.read_bytes(),
            mode="evidence",
            top_k=config.top_k,
            runs_dir=run_artifact_root,
            pipeline=active_pipeline,
        )
        run_id = detail.run.run_id

    manifest_payload = {
        "artifact_type": "wafer_user_study_manifest_v1",
        "evidence_path": evidence_path.as_posix(),
        "baseline_path": baseline_path.as_posix(),
        "graph_output_dir": graph_output_dir.as_posix(),
        "run_artifact_root": run_artifact_root.as_posix(),
        "run_id": run_id,
        "case": {
            "case_id": evidence.case_id,
            "dataset": evidence.dataset,
            "anomaly_type": evidence.anomaly_type,
            "location": evidence.location,
            "morphology": evidence.morphology,
        },
        "graph_summary": graph_summary,
        "runtime_kg_import": runtime_kg_import,
    }
    _write_json(manifest_path, manifest_payload, overwrite=config.overwrite)

    return WaferUserStudyResult(
        evidence_path=evidence_path,
        baseline_path=baseline_path,
        graph_output_dir=graph_output_dir,
        manifest_path=manifest_path,
        run_id=run_id,
        graph_summary=graph_summary,
        runtime_kg_import=runtime_kg_import,
    )


def materialize_wafer_user_study_graph(
    graph: KnowledgeGraph,
    *,
    evidence: Evidence,
    output_dir: Path,
    overwrite: bool = False,
    graph_scope: GraphScope = "full_runtime",
    graph_hops: int = 2,
) -> dict[str, Any]:
    """Write wafer KG Studio graph artifacts for user-study consumption."""
    if graph_hops < 1:
        raise ValueError("graph_hops must be >= 1")
    _ensure_writable_output_dir(output_dir, overwrite=overwrite)

    focus_node_ids = _resolve_focus_node_ids(graph, evidence)
    if graph_scope == "full_runtime":
        selected_nodes, selected_edges = _select_wafer_runtime_graph(graph)
    else:
        selected_nodes, selected_edges, focus_node_ids = _select_wafer_user_study_subgraph(
            graph,
            evidence=evidence,
            graph_hops=graph_hops,
        )
    nodes_path = output_dir / "nodes.csv"
    edges_path = output_dir / "edges.csv"
    summary_path = output_dir / "kg_construction_summary.json"
    manifest_path = output_dir / "kg_construction_manifest.json"
    build_summary_path = output_dir / "source_kg_build_summary.json"
    build_manifest_path = output_dir / "source_kg_build_manifest.json"
    created_at = datetime.now(timezone.utc).isoformat()
    build_run_id = f"wafer_user_study:{evidence.case_id}"

    _write_nodes_csv(nodes_path, selected_nodes)
    _write_edges_csv(edges_path, selected_edges)

    summary_payload = {
        "artifact_type": USER_STUDY_GRAPH_ARTIFACT_TYPE,
        "status": "ready",
        "created_at": created_at,
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "anomaly_type": evidence.anomaly_type,
        "graph_scope": graph_scope,
        "focus_node_ids": focus_node_ids,
        "node_count": len(selected_nodes),
        "edge_count": len(selected_edges),
        "scenario_counts": dict(Counter(edge.scenario for edge in selected_edges)),
        "source_counts": dict(Counter(edge.source for edge in selected_edges)),
        "review_status_counts": dict(
            Counter(edge.review_status for edge in selected_edges)
        ),
        "note": (
            "Full wafer runtime graph slice for user study and KG Studio review; "
            "candidate/plausible explanation only; not a verified root-cause label."
            if graph_scope == "full_runtime"
            else "Focused wafer user-study candidate graph for KG Studio review; "
            "candidate/plausible explanation only; not a verified root-cause label."
        ),
    }
    manifest_payload = {
        "artifact_type": USER_STUDY_GRAPH_ARTIFACT_TYPE,
        "run": {"run_id": build_run_id},
        "summary": {
            "node_count": len(selected_nodes),
            "edge_count": len(selected_edges),
        },
        "case": {
            "case_id": evidence.case_id,
            "dataset": evidence.dataset,
            "anomaly_type": evidence.anomaly_type,
        },
        "artifacts": {
            "nodes": nodes_path.as_posix(),
            "edges": edges_path.as_posix(),
            "summary": summary_path.as_posix(),
        },
        "focus_nodes": focus_node_ids,
        "sources": [],
        "draft_rows": [],
        "review_decisions": [],
    }
    build_summary_payload = {
        "artifact_type": "source_kg_compiler_build_summary_v1",
        "run_id": build_run_id,
        "status": "built",
        "created_at": created_at,
        "output_dir": output_dir.as_posix(),
        "source_count": 1,
        "source_ids": [evidence.case_id],
        "node_count": len(selected_nodes),
        "edge_count": len(selected_edges),
        "claim_boundary": summary_payload["note"],
    }
    build_manifest_payload = {
        **manifest_payload,
        "artifact_type": "source_to_kg_construction_manifest_v1",
    }

    _write_json(summary_path, summary_payload, overwrite=True)
    _write_json(manifest_path, manifest_payload, overwrite=True)
    _write_json(build_summary_path, build_summary_payload, overwrite=True)
    _write_json(build_manifest_path, build_manifest_payload, overwrite=True)
    return {
        "nodes_path": nodes_path.as_posix(),
        "edges_path": edges_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "build_summary_path": build_summary_path.as_posix(),
        "build_manifest_path": build_manifest_path.as_posix(),
        **summary_payload,
    }


def _load_wafer_user_study_evidence(path: Path) -> Evidence:
    _require_existing_file(path, label="wafer user-study evidence")
    evidence = load_evidence_json(path)
    if evidence.dataset != "wafer":
        raise ValueError(f"wafer user-study evidence must use dataset='wafer': {path}")
    return evidence


def _runtime_kg_import_payload(graph: KnowledgeGraph) -> dict[str, Any]:
    summary = import_knowledge_graph_with_config(graph, resolve_neo4j_config())
    return _import_summary_payload(summary)


def _import_summary_payload(summary: ImportSummary) -> dict[str, Any]:
    return {
        "node_count": summary.node_count,
        "edge_count": summary.edge_count,
        "dry_run": summary.dry_run,
    }


def _select_wafer_runtime_graph(
    graph: KnowledgeGraph,
) -> tuple[list[KGNode], list[KGEdge]]:
    selected_nodes = [
        node for node in graph.nodes.values() if node.scenario in {"wafer", "shared"}
    ]
    selected_node_ids = {node.id for node in selected_nodes}
    selected_edges = [
        edge
        for edge in graph.edges
        if edge.scenario in {"wafer", "shared"}
        and edge.head in selected_node_ids
        and edge.tail in selected_node_ids
    ]
    selected_nodes.sort(key=lambda node: (node.scenario, node.id))
    selected_edges.sort(
        key=lambda edge: (
            0 if edge.review_status == "reviewed" else 1,
            -edge.confidence,
            edge.edge_id,
        )
    )
    return selected_nodes, selected_edges


def _select_wafer_user_study_subgraph(
    graph: KnowledgeGraph,
    *,
    evidence: Evidence,
    graph_hops: int,
) -> tuple[list[KGNode], list[KGEdge], list[str]]:
    focus_node_ids = _resolve_focus_node_ids(graph, evidence)
    if not focus_node_ids:
        raise ValueError(
            f"no wafer KG nodes matched anomaly_type={evidence.anomaly_type!r}"
        )

    selected_node_ids = set(focus_node_ids)
    frontier = set(focus_node_ids)
    candidate_edges = [
        edge for edge in graph.edges if edge.scenario in {"wafer", "shared"}
    ]
    for _ in range(graph_hops):
        next_frontier: set[str] = set()
        for edge in candidate_edges:
            if edge.head in frontier or edge.tail in frontier:
                next_frontier.add(edge.head)
                next_frontier.add(edge.tail)
        next_frontier -= selected_node_ids
        selected_node_ids.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    selected_edges = [
        edge
        for edge in candidate_edges
        if edge.head in selected_node_ids and edge.tail in selected_node_ids
    ]
    selected_nodes = [graph.nodes[node_id] for node_id in sorted(selected_node_ids)]
    selected_edges.sort(
        key=lambda edge: (
            0 if edge.review_status == "reviewed" else 1,
            -edge.confidence,
            edge.edge_id,
        )
    )
    return selected_nodes, selected_edges, sorted(focus_node_ids)


def _resolve_focus_node_ids(graph: KnowledgeGraph, evidence: Evidence) -> list[str]:
    target = _normalized_token(evidence.anomaly_type)
    if not target:
        return []

    exact: list[str] = []
    fuzzy: list[str] = []
    for node in graph.nodes.values():
        if node.scenario not in {"wafer", "shared"}:
            continue
        terms = {
            _normalized_token(node.id),
            _normalized_token(node.name),
            *(_normalized_token(alias) for alias in node.aliases),
        }
        if target in terms:
            exact.append(node.id)
            continue
        if any(target in term or term in target for term in terms if term):
            fuzzy.append(node.id)
    return exact or fuzzy


def _normalized_token(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _write_nodes_csv(path: Path, nodes: list[KGNode]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "name", "label", "scenario", "aliases", "description"],
        )
        writer.writeheader()
        for node in nodes:
            writer.writerow(
                {
                    "id": node.id,
                    "name": node.name,
                    "label": node.label,
                    "scenario": node.scenario,
                    "aliases": "|".join(node.aliases),
                    "description": node.description,
                }
            )


def _write_edges_csv(path: Path, edges: list[KGEdge]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "head",
        "relation",
        "tail",
        "scenario",
        "source",
        "evidence",
        "confidence",
        "weight",
        "review_status",
        "feedback_count",
        "accepted_count",
        "rejected_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for edge in edges:
            writer.writerow(
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "scenario": edge.scenario,
                    "source": edge.source,
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "weight": edge.weight,
                    "review_status": edge.review_status,
                    "feedback_count": edge.feedback_count,
                    "accepted_count": edge.accepted_count,
                    "rejected_count": edge.rejected_count,
                }
            )


def _write_json(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _require_existing_file(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")


def _ensure_writable_output_dir(path: Path, *, overwrite: bool) -> None:
    sentinel_paths = [
        path / "nodes.csv",
        path / "edges.csv",
        path / "kg_construction_summary.json",
        path / "kg_construction_manifest.json",
    ]
    if not overwrite and any(item.exists() for item in sentinel_paths):
        raise ValueError(
            f"wafer user-study graph output already exists: {path}; pass overwrite=True"
        )
    path.mkdir(parents=True, exist_ok=True)


__all__ = [
    "DEFAULT_WAFER_USER_STUDY_BASELINE_PATH",
    "DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH",
    "DEFAULT_WAFER_USER_STUDY_GRAPH_DIR",
    "DEFAULT_WAFER_USER_STUDY_MANIFEST_PATH",
    "WaferUserStudyConfig",
    "WaferUserStudyResult",
    "materialize_wafer_user_study_graph",
    "prepare_wafer_user_study",
]
