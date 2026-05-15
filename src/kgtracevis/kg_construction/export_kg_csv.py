"""KG CSV export utilities."""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Iterable
from pathlib import Path

from kgtracevis.kg.graph import (
    OPTIONAL_RCA_EDGE_COLUMNS,
    REQUIRED_EDGE_COLUMNS,
    REQUIRED_NODE_COLUMNS,
    KGEdge,
    KGNode,
)
from kgtracevis.kg_construction.confidence_assigner import edge_weight

NODE_COLUMNS = ["id", "name", "label", "scenario", "aliases", "description"]
EDGE_COLUMNS = [
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
    "relation_family",
    "propagation_enabled",
    "propagation_direction",
    "propagation_priority",
    "attenuation",
    "edge_weight",
    "root_candidate",
    "observable",
    "event_anchor",
    "fault_anchor",
    "task_view",
    "confidence_policy",
    "source_trust",
    "rca_score",
    "rca_score_confidence",
    "rca_score_priority",
    "rca_score_attenuation",
    "rca_score_source_trust",
    "external_edge_id",
    "kg_build_id",
]
VALID_SCENARIOS = {"mvtec", "tep", "wafer", "shared"}
VALID_REVIEW_STATUS = {"auto", "reviewed", "rejected"}

if set(NODE_COLUMNS) != REQUIRED_NODE_COLUMNS:  # pragma: no cover - import-time guard.
    raise RuntimeError("node export columns diverged from KG loader contract")
if not REQUIRED_EDGE_COLUMNS.issubset(set(EDGE_COLUMNS)):  # pragma: no cover.
    raise RuntimeError("edge export columns diverged from KG loader contract")
if not OPTIONAL_RCA_EDGE_COLUMNS.issubset(set(EDGE_COLUMNS)):  # pragma: no cover.
    raise RuntimeError("RCA edge export columns diverged from KG loader contract")


def export_nodes_csv(nodes: Iterable[KGNode], path: str | Path) -> None:
    """Export nodes using the KG node CSV contract."""
    node_rows = list(nodes)
    validate_nodes(node_rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NODE_COLUMNS)
        writer.writeheader()
        for node in sorted(node_rows, key=lambda item: item.id):
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


def export_edges_csv(edges: Iterable[KGEdge], path: str | Path) -> None:
    """Export edges using the KG edge CSV contract."""
    edge_rows = list(edges)
    validate_edges(edge_rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDGE_COLUMNS)
        writer.writeheader()
        for edge in sorted(edge_rows, key=lambda item: item.edge_id):
            writer.writerow(
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "scenario": edge.scenario,
                    "source": edge.source,
                    "evidence": edge.evidence,
                    "confidence": f"{edge.confidence:.6g}",
                    "weight": f"{edge.weight:.6g}",
                    "review_status": edge.review_status,
                    "feedback_count": edge.feedback_count,
                    "accepted_count": edge.accepted_count,
                    "rejected_count": edge.rejected_count,
                    "relation_family": edge.relation_family,
                    "propagation_enabled": _bool_csv(edge.propagation_enabled),
                    "propagation_direction": edge.propagation_direction,
                    "propagation_priority": _number_csv(edge.propagation_priority),
                    "attenuation": _number_csv(edge.attenuation),
                    "edge_weight": _number_csv(
                        edge.edge_weight if edge.edge_weight is not None else edge.weight
                    ),
                    "root_candidate": _bool_csv(edge.root_candidate),
                    "observable": _bool_csv(edge.observable),
                    "event_anchor": edge.event_anchor,
                    "fault_anchor": edge.fault_anchor,
                    "task_view": edge.task_view,
                    "confidence_policy": edge.confidence_policy,
                    "source_trust": _number_csv(edge.source_trust),
                    "rca_score": _number_csv(edge.rca_score),
                    "rca_score_confidence": _number_csv(edge.rca_score_confidence),
                    "rca_score_priority": _number_csv(edge.rca_score_priority),
                    "rca_score_attenuation": _number_csv(edge.rca_score_attenuation),
                    "rca_score_source_trust": _number_csv(edge.rca_score_source_trust),
                    "external_edge_id": edge.external_edge_id,
                    "kg_build_id": edge.kg_build_id,
                }
            )


def export_kg_csv(
    nodes: Iterable[KGNode],
    edges: Iterable[KGEdge],
    *,
    nodes_path: str | Path,
    edges_path: str | Path,
) -> None:
    """Export node and edge CSV files."""
    node_rows = list(nodes)
    edge_rows = list(edges)
    validate_kg_csv_contract(node_rows, edge_rows)
    export_nodes_csv(node_rows, nodes_path)
    export_edges_csv(edge_rows, edges_path)


def validate_nodes(nodes: Iterable[KGNode]) -> None:
    """Validate KG nodes against the node CSV contract."""
    seen_ids: set[str] = set()
    for node in nodes:
        if not node.id.strip():
            raise ValueError("node id is required")
        if node.id in seen_ids:
            raise ValueError(f"duplicate node id: {node.id}")
        seen_ids.add(node.id)
        if not _is_pascal_case(node.id):
            raise ValueError(f"node id must use PascalCase: {node.id}")
        if not node.name.strip():
            raise ValueError(f"node name is required for {node.id}")
        if not node.label.strip():
            raise ValueError(f"node label is required for {node.id}")
        if node.scenario.strip() not in VALID_SCENARIOS:
            raise ValueError(f"invalid node scenario for {node.id}: {node.scenario}")


def validate_edges(edges: Iterable[KGEdge]) -> None:
    """Validate KG edges against the edge CSV contract."""
    seen_ids: set[str] = set()
    for edge in edges:
        if edge.edge_id in seen_ids:
            raise ValueError(f"duplicate edge id: {edge.edge_id}")
        seen_ids.add(edge.edge_id)
        if not _is_pascal_case(edge.head):
            raise ValueError(f"edge head must use PascalCase for {edge.edge_id}: {edge.head}")
        if not _is_pascal_case(edge.tail):
            raise ValueError(f"edge tail must use PascalCase for {edge.edge_id}: {edge.tail}")
        if not _is_upper_snake(edge.relation):
            raise ValueError(f"edge relation must use uppercase snake case: {edge.edge_id}")
        if edge.scenario.strip() not in VALID_SCENARIOS:
            raise ValueError(f"invalid edge scenario for {edge.edge_id}: {edge.scenario}")
        if not edge.source.strip():
            raise ValueError(f"edge source is required for {edge.edge_id}")
        if not edge.evidence.strip():
            raise ValueError(f"edge evidence is required for {edge.edge_id}")
        if not 0.0 <= float(edge.confidence) <= 1.0:
            raise ValueError(f"confidence must be in [0, 1] for {edge.edge_id}: {edge.confidence}")
        expected_weight = edge_weight(edge.confidence)
        if not math.isclose(float(edge.weight), expected_weight, abs_tol=1e-6):
            raise ValueError(
                f"edge weight must equal 1 - confidence for {edge.edge_id}: "
                f"{edge.weight} != {expected_weight}"
            )
        if edge.review_status.strip() not in VALID_REVIEW_STATUS:
            raise ValueError(f"invalid review_status for {edge.edge_id}: {edge.review_status}")
        feedback_counts = (edge.feedback_count, edge.accepted_count, edge.rejected_count)
        if any(value < 0 for value in feedback_counts):
            raise ValueError(f"feedback counters must be non-negative for {edge.edge_id}")


def validate_kg_csv_contract(nodes: Iterable[KGNode], edges: Iterable[KGEdge]) -> None:
    """Validate nodes and edges before publishing or summarizing KG CSV data."""
    validate_nodes(nodes)
    validate_edges(edges)


def _is_pascal_case(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9]*", value.strip()))


def _is_upper_snake(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*", value.strip()))


def _bool_csv(value: bool) -> str:
    return "true" if value else "false"


def _number_csv(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.6g}"
