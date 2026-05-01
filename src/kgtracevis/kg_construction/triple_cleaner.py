"""Candidate triple cleaning utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable

from kgtracevis.kg.graph import KGEdge, KGNode, normalize_text
from kgtracevis.kg_construction.candidate_entity_extractor import CandidateEntity
from kgtracevis.kg_construction.candidate_triple_extractor import CandidateTriple
from kgtracevis.kg_construction.confidence_assigner import edge_weight

VALID_SCENARIOS = {"mvtec", "tep", "wafer", "shared"}
VALID_REVIEW_STATUS = {"auto", "reviewed", "rejected"}


def clean_candidate_nodes(candidates: Iterable[CandidateEntity | KGNode]) -> list[KGNode]:
    """Trim, validate, and deduplicate candidate nodes."""
    by_id: dict[str, KGNode] = {}
    identity_to_id: dict[str, str] = {}
    for candidate in candidates:
        if isinstance(candidate, CandidateEntity):
            candidate_node = candidate.to_kg_node()
        else:
            candidate_node = candidate
        node = _normalize_node(candidate_node)
        existing = by_id.get(node.id)
        if existing is not None:
            by_id[node.id] = _merge_nodes(existing, node)
            continue
        duplicate_id = _find_duplicate_node_id(node, identity_to_id)
        if duplicate_id is not None:
            by_id[duplicate_id] = _merge_nodes(by_id[duplicate_id], node)
            _index_node_identities(by_id[duplicate_id], identity_to_id)
            continue
        by_id[node.id] = node
        _index_node_identities(node, identity_to_id)
    return sorted(by_id.values(), key=lambda item: item.id)


def clean_candidate_triples(
    candidates: Iterable[CandidateTriple | KGEdge],
    *,
    existing_edges: Iterable[KGEdge] = (),
    allow_reviewed_overwrite: bool = False,
) -> list[KGEdge]:
    """Trim, validate, and deduplicate candidate triples.

    Existing reviewed edges are protected from conflicting candidate overwrites
    unless explicitly allowed.
    """
    protected = {edge.edge_id: edge for edge in existing_edges}
    cleaned: dict[str, KGEdge] = {}
    for candidate in candidates:
        edge = _normalize_edge(
            candidate.to_kg_edge() if isinstance(candidate, CandidateTriple) else candidate
        )
        existing = protected.get(edge.edge_id)
        if existing is not None and existing != edge:
            if existing.review_status == "reviewed" and not allow_reviewed_overwrite:
                raise ValueError(f"refusing to overwrite reviewed edge {edge.edge_id}")
        merged_edge = cleaned.get(edge.edge_id)
        if merged_edge is None:
            cleaned[edge.edge_id] = edge
            continue
        if merged_edge == edge:
            continue
        if merged_edge.review_status == "reviewed" and not allow_reviewed_overwrite:
            raise ValueError(f"refusing to overwrite reviewed edge {edge.edge_id}")
        if edge.review_status == "reviewed" or merged_edge.review_status != "reviewed":
            cleaned[edge.edge_id] = edge
    return sorted(cleaned.values(), key=lambda item: item.edge_id)


def _normalize_node(node: KGNode) -> KGNode:
    scenario = node.scenario.strip()
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"invalid node scenario for {node.id}: {scenario}")
    aliases = tuple(dict.fromkeys(alias.strip() for alias in node.aliases if alias.strip()))
    return KGNode(
        id=_pascal_case(node.id.strip() or node.name),
        name=node.name.strip(),
        label=node.label.strip(),
        scenario=scenario,
        aliases=aliases,
        description=node.description.strip(),
    )


def _normalize_edge(edge: KGEdge) -> KGEdge:
    scenario = edge.scenario.strip()
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"invalid edge scenario for {edge.edge_id}: {scenario}")
    review_status = edge.review_status.strip()
    if review_status not in VALID_REVIEW_STATUS:
        raise ValueError(f"invalid review_status for {edge.edge_id}: {review_status}")
    confidence = float(edge.confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1] for {edge.edge_id}: {confidence}")
    feedback_counts = (edge.feedback_count, edge.accepted_count, edge.rejected_count)
    if any(value < 0 for value in feedback_counts):
        raise ValueError(f"feedback counters must be non-negative for {edge.edge_id}")
    if not edge.source.strip():
        raise ValueError(f"edge source is required for {edge.edge_id}")
    if not edge.evidence.strip():
        raise ValueError(f"edge evidence is required for {edge.edge_id}")
    return KGEdge(
        head=_pascal_case(edge.head.strip()),
        relation=_upper_snake(edge.relation),
        tail=_pascal_case(edge.tail.strip()),
        scenario=scenario,
        source=edge.source.strip(),
        evidence=edge.evidence.strip(),
        confidence=confidence,
        weight=edge_weight(confidence),
        review_status=review_status,
        feedback_count=edge.feedback_count,
        accepted_count=edge.accepted_count,
        rejected_count=edge.rejected_count,
    )


def _merge_nodes(left: KGNode, right: KGNode) -> KGNode:
    if left.label != right.label or left.scenario != right.scenario:
        raise ValueError(f"conflicting node definition for {left.id}")
    aliases = tuple(dict.fromkeys((*left.aliases, *right.aliases)))
    description = left.description or right.description
    return KGNode(
        id=left.id,
        name=left.name or right.name,
        label=left.label,
        scenario=left.scenario,
        aliases=aliases,
        description=description,
    )


def _find_duplicate_node_id(node: KGNode, identity_to_id: dict[str, str]) -> str | None:
    for identity in _node_identities(node):
        existing = identity_to_id.get(identity)
        if existing is not None:
            return existing
    return None


def _index_node_identities(node: KGNode, identity_to_id: dict[str, str]) -> None:
    for identity in _node_identities(node):
        identity_to_id[identity] = node.id


def _node_identities(node: KGNode) -> set[str]:
    identities: set[str] = set()
    for term in (node.id, node.name, *node.aliases):
        normalized = normalize_text(term)
        if normalized:
            identities.add(normalized)
    return identities


def _upper_snake(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        raise ValueError("relation is required")
    return "_".join(word.upper() for word in words)


def _pascal_case(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        raise ValueError("node id is required")
    return "".join(word[:1].upper() + word[1:] for word in words)
