# mypy: ignore-errors
"""Propagation graph utilities for Root-KGD-style RCA."""

# ruff: noqa

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from kgtracevis.workflows.tep_root_kgd.assets import read_jsonl


RELATION_LOGIT_PRIORS = {
    "FAULT_SOURCE": 1.65,
    "CONTROL": 1.35,
    "MATERIAL_FLOW": 1.05,
    "ENERGY_TRANSFER": 0.75,
    "PHASE_CHANGE": 0.55,
    "COMPOSITION": 0.70,
    "OBSERVATION": 0.35,
}

DEFAULT_RELATION_PARAMS = {
    "FAULT_SOURCE": {"sigma": 0.10, "priority": 7},
    "CONTROL": {"sigma": 0.14, "priority": 6},
    "MATERIAL_FLOW": {"sigma": 0.20, "priority": 5},
    "ENERGY_TRANSFER": {"sigma": 0.26, "priority": 4},
    "PHASE_CHANGE": {"sigma": 0.30, "priority": 3},
    "COMPOSITION": {"sigma": 0.24, "priority": 2},
    "OBSERVATION": {"sigma": 0.32, "priority": 1},
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        scale = math.exp(-value)
        return 1.0 / (1.0 + scale)
    scale = math.exp(value)
    return scale / (1.0 + scale)


def default_relation_params() -> dict[str, dict[str, float]]:
    return {
        family: {"sigma": values["sigma"], "priority": values["priority"]}
        for family, values in DEFAULT_RELATION_PARAMS.items()
    }


def load_alignment_scores(project_root: Path) -> dict[str, float]:
    path = project_root / "data" / "processed" / "kg" / "entity_alignment_edges.jsonl"
    if not path.exists():
        return {}
    scores: dict[str, float] = {}
    for row in read_jsonl(path):
        scores[str(row["tail_id"])] = max(
            float(row.get("confidence", 0.0)),
            scores.get(str(row["tail_id"]), 0.0),
        )
    return scores


def initial_edge_weight(edge: dict[str, object], alignment_scores: dict[str, float]) -> float:
    relation_family = str(edge.get("relation_family", ""))
    confidence = float(edge.get("confidence", 0.0))
    support_count = float(edge.get("support_count", 0.0))
    source_types = {str(item) for item in edge.get("source_types", [])}
    evidence_quality = clamp(math.log1p(support_count) / math.log1p(8.0))
    source_agreement = 1.0 if "prior" in source_types else 0.75 if len(source_types) > 1 else 0.55
    projection_confidence = 1.0 if str(edge.get("edge_origin", "")) in {"semantic_lift", "rca_graph"} else 0.7
    head_alignment = alignment_scores.get(str(edge.get("head_id", "")), 0.5)
    tail_alignment = alignment_scores.get(str(edge.get("tail_id", "")), 0.5)
    alignment_confidence = (head_alignment + tail_alignment) / 2.0
    logit = (
        RELATION_LOGIT_PRIORS.get(relation_family, 0.0)
        + 1.20 * (confidence - 0.5)
        + 0.75 * (evidence_quality - 0.5)
        + 0.45 * (source_agreement - 0.5)
        + 0.30 * (projection_confidence - 0.5)
        + 0.45 * (alignment_confidence - 0.5)
    )
    return round(clamp(sigmoid(logit)), 6)


def build_propagation_graph(
    project_root: Path,
    *,
    edge_weights: dict[str, float] | None = None,
    relation_params: dict[str, dict[str, float]] | None = None,
) -> dict[str, object]:
    nodes = {
        str(row["entity_id"]): row
        for row in read_jsonl(project_root / "data" / "processed" / "rca" / "nodes.jsonl")
    }
    alignment_scores = load_alignment_scores(project_root)
    params = relation_params or default_relation_params()
    propagation_edges = []
    for row in read_jsonl(project_root / "data" / "processed" / "rca" / "edges.jsonl"):
        if not bool(row.get("propagation_enabled", False)):
            continue
        edge_id = str(row["edge_id"])
        propagation_edges.append(
            {
                **row,
                "edge_id": edge_id,
                "edge_weight": (
                    round(float(edge_weights[edge_id]), 6)
                    if edge_weights and edge_id in edge_weights
                    else initial_edge_weight(row, alignment_scores)
                ),
            }
        )
    outgoing: dict[str, list[dict[str, object]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, object]]] = defaultdict(list)
    for edge in propagation_edges:
        outgoing[str(edge["head_id"])].append(edge)
        incoming[str(edge["tail_id"])].append(edge)
    for edge_list in outgoing.values():
        edge_list.sort(
            key=lambda edge: (
                -int(params[str(edge["relation_family"])]["priority"]),
                str(edge["tail_id"]),
                str(edge["edge_id"]),
            )
        )
    return {
        "nodes": nodes,
        "edges": {str(edge["edge_id"]): edge for edge in propagation_edges},
        "outgoing": dict(outgoing),
        "incoming": dict(incoming),
        "relation_params": params,
    }


def candidate_source_ids(graph: dict[str, object], allowed_types: Iterable[str]) -> set[str]:
    allowed = {str(item) for item in allowed_types}
    explicit_candidates = {
        node_id
        for node_id, row in graph["nodes"].items()
        if bool(row.get("root_cause_candidate", False)) and graph["outgoing"].get(node_id)
    }
    if explicit_candidates:
        return explicit_candidates
    return {
        node_id
        for node_id, row in graph["nodes"].items()
        if row.get("entity_type") in allowed and graph["outgoing"].get(node_id)
    }


def incident_neighbors(graph: dict[str, object], node_id: str) -> list[tuple[str, dict[str, object]]]:
    neighbors: list[tuple[str, dict[str, object]]] = []
    for edge in graph["outgoing"].get(node_id, []):
        neighbors.append((str(edge["tail_id"]), edge))
    for edge in graph["incoming"].get(node_id, []):
        neighbors.append((str(edge["head_id"]), edge))
    return neighbors


def simulate_propagation(
    graph: dict[str, object],
    source_id: str,
    *,
    seed_score: float,
    max_hops: int = 4,
    epsilon: float = 1e-6,
    global_cap: float = 1.0,
) -> dict[str, object]:
    relation_params = graph["relation_params"]
    family_order = sorted(
        relation_params,
        key=lambda family: (-int(relation_params[family]["priority"]), family),
    )
    node_scores: dict[str, float] = {source_id: float(seed_score)}
    frontier: dict[str, float] = {source_id: float(seed_score)}
    edge_flow: dict[str, float] = defaultdict(float)
    receive_counts: dict[tuple[str, str], int] = {}
    best_parent_gain: dict[str, float] = {}
    best_parent_edge: dict[str, str] = {}

    for hop in range(1, max_hops + 1):
        next_frontier: dict[str, float] = defaultdict(float)
        hop_gain = 0.0
        for family in family_order:
            attenuation = math.exp(-float(relation_params[family]["sigma"]) * hop)
            for node_id, node_signal in sorted(frontier.items()):
                for edge in graph["outgoing"].get(node_id, []):
                    if str(edge["relation_family"]) != family:
                        continue
                    tail_id = str(edge["tail_id"])
                    receive_key = (tail_id, family)
                    receive_count = receive_counts.get(receive_key, 0) + 1
                    delta = (
                        float(node_signal)
                        * float(edge["edge_weight"])
                        * attenuation
                        / max(1, receive_count)
                    )
                    if delta <= epsilon:
                        continue
                    already_allocated = float(node_scores.get(tail_id, 0.0)) + float(next_frontier.get(tail_id, 0.0))
                    available_capacity = max(0.0, global_cap - already_allocated)
                    if available_capacity <= epsilon:
                        continue
                    if delta > available_capacity:
                        delta = available_capacity
                    if delta <= epsilon:
                        continue
                    receive_counts[receive_key] = receive_count
                    next_frontier[tail_id] += delta
                    edge_flow[str(edge["edge_id"])] += delta
                    hop_gain += delta
                    if delta > best_parent_gain.get(tail_id, 0.0):
                        best_parent_gain[tail_id] = delta
                        best_parent_edge[tail_id] = str(edge["edge_id"])
        if hop_gain <= epsilon:
            break
        for node_id, delta in next_frontier.items():
            node_scores[node_id] = float(node_scores.get(node_id, 0.0)) + float(delta)
        frontier = dict(next_frontier)

    return {
        "node_scores": {node_id: round(score, 8) for node_id, score in node_scores.items()},
        "edge_flow": {edge_id: round(score, 8) for edge_id, score in edge_flow.items()},
        "best_parent_edge": best_parent_edge,
    }


def trace_path(
    source_id: str,
    target_id: str,
    best_parent_edge: dict[str, str],
    edges_by_id: dict[str, dict[str, object]],
    *,
    max_depth: int = 12,
) -> list[str]:
    if source_id == target_id:
        return []
    path: list[str] = []
    current = target_id
    visited = {current}
    for _ in range(max_depth):
        edge_id = best_parent_edge.get(current)
        if not edge_id:
            return []
        edge = edges_by_id[edge_id]
        path.append(edge_id)
        current = str(edge["head_id"])
        if current == source_id:
            path.reverse()
            return path
        if current in visited:
            return []
        visited.add(current)
    return []
