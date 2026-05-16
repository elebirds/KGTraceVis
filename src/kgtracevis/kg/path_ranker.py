"""Relation-weighted root-cause path ranking helpers."""

from __future__ import annotations

import hashlib
from typing import Any

import networkx as nx

from kgtracevis.kg.entity_linker import selected_entities_by_field
from kgtracevis.kg.graph import KGEdge, KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence

ROOT_CAUSE_LABELS = {
    "CandidateCause",
    "CauseCategory",
    "Fault",
    "FaultType",
    "Mechanism",
    "RootCause",
}
SOURCE_FIELDS = {"anomaly_type", "variable", "log_event"}


def rank_root_cause_paths(
    evidence: Evidence,
    graph: KnowledgeGraph,
    linked_entities: list[dict[str, Any]],
    *,
    top_k: int = 5,
    max_depth: int = 5,
    alpha: float = 0.55,
    beta: float = 0.35,
    gamma: float = 0.10,
) -> list[dict[str, Any]]:
    """Rank candidate RCA paths using relation confidence and evidence match."""
    if _is_non_anomalous_type(evidence.anomaly_type):
        return []

    selected = selected_entities_by_field(linked_entities)
    selected_ids = set(selected.values())
    source_ids = {
        entity_id
        for field, entity_id in selected.items()
        if field in SOURCE_FIELDS and graph.node_in_scope(entity_id, evidence.dataset)
    }
    target_ids = {
        node.id
        for node in graph.nodes.values()
        if node.scenario in {evidence.dataset, "shared"}
        and (node.label in ROOT_CAUSE_LABELS or node.id.endswith("Cause"))
    }

    ranked: list[dict[str, Any]] = []
    for source_id in sorted(source_ids):
        for target_id in sorted(target_ids - {source_id}):
            for path in _simple_paths(graph, source_id, target_id, max_depth):
                if not all(graph.node_in_scope(node_id, evidence.dataset) for node_id in path):
                    continue
                edges = _path_edges(graph, path, scenario=evidence.dataset)
                if not edges:
                    continue
                relations = [edge.relation for edge in edges]
                conf = sum(edge.confidence for edge in edges) / len(edges)
                rca_score = _path_rca_score(edges)
                path_strength = _path_strength(edges)
                evidence_match = len(set(path) & selected_ids) / max(1, len(selected_ids))
                length_penalty = (len(path) - 1) / max_depth
                score = alpha * path_strength + beta * evidence_match - gamma * length_penalty
                ranked.append(
                    {
                        "path_id": "",
                        "source_entity_id": source_id,
                        "target_entity_id": target_id,
                        "nodes": path,
                        "node_names": [graph.nodes[node_id].name for node_id in path],
                        "relations": relations,
                        "score": round(score, 4),
                        "confidence": round(conf, 4),
                        "path_strength": round(path_strength, 4),
                        "rca_score": round(rca_score, 4),
                        "evidence_match": round(evidence_match, 4),
                        "length": len(path) - 1,
                        "supporting_evidence": [edge.evidence for edge in edges],
                        "source_edge_ids": [edge.edge_id for edge in edges],
                        "source_edges": [edge.model_dump() for edge in edges],
                        "kg_build_ids": _path_kg_build_ids(edges),
                    }
                )

    ranked.sort(key=lambda item: (-float(item["score"]), item["nodes"]))
    for item in ranked[:top_k]:
        item["path_id"] = _path_id(
            evidence.case_id,
            item["nodes"],
            item["relations"],
        )
    return ranked[:top_k]


def _simple_paths(
    graph: KnowledgeGraph,
    source_id: str,
    target_id: str,
    max_depth: int,
) -> list[list[str]]:
    try:
        return list(
            nx.all_simple_paths(
                graph.graph,
                source=source_id,
                target=target_id,
                cutoff=max_depth,
            )
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def _path_edges(
    graph: KnowledgeGraph,
    path: list[str],
    *,
    scenario: str | None = None,
) -> list[KGEdge]:
    edges: list[KGEdge] = []
    for head, tail in zip(path, path[1:], strict=False):
        edge_options = graph.edge_between(head, tail, scenario=scenario)
        if not edge_options:
            return []
        edges.append(max(edge_options, key=_edge_rank_key))
    return edges


def _path_strength(edges: list[KGEdge]) -> float:
    return sum(_edge_strength(edge) for edge in edges) / len(edges)


def _path_rca_score(edges: list[KGEdge]) -> float:
    scores = [edge.rca_score for edge in edges if edge.rca_score > 0]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _path_kg_build_ids(edges: list[KGEdge]) -> list[str]:
    return sorted({edge.kg_build_id for edge in edges if edge.kg_build_id})


def _edge_strength(edge: KGEdge) -> float:
    if edge.rca_score > 0:
        return edge.rca_score
    if edge.edge_weight is not None and edge.propagation_enabled:
        return _clamp01(1.0 - edge.edge_weight)
    return edge.confidence


def _edge_rank_key(edge: KGEdge) -> tuple[float, float]:
    return (_edge_strength(edge), edge.confidence)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _path_id(case_id: str, nodes: list[str], relations: list[str]) -> str:
    signature = "|".join((*nodes, *relations))
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
    return f"path_{case_id}_{digest}"


def _is_non_anomalous_type(value: str | None) -> bool:
    if value is None:
        return True
    token = "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
    return token in {"", "good", "normal", "none", "unknown", "no_label", "unlabeled"}
