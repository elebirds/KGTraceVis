"""Review queue generation for candidate RCA-KG artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kgtracevis.kg.graph import KGEdge
from kgtracevis.kg_construction.alignment import AlignmentResult


@dataclass(frozen=True)
class ReviewQueueItem:
    """One prioritized human review item."""

    target_key: str
    item_type: str
    priority: int
    reason: str
    candidate_payload: dict[str, Any]
    source: str
    evidence: str
    confidence: float
    scenario: str
    relation_family: str
    graph_impact: str
    recommended_action: str


def build_review_queue(
    edges: tuple[KGEdge, ...],
    *,
    alignment: AlignmentResult | None = None,
) -> tuple[ReviewQueueItem, ...]:
    """Build review items from RCA edge risk and alignment conflicts."""
    items: list[ReviewQueueItem] = []
    if alignment is not None:
        for conflict in alignment.conflicts:
            items.append(
                ReviewQueueItem(
                    target_key=f"alignment_conflict:{conflict.get('identity')}",
                    item_type="entity_merge_conflict",
                    priority=95,
                    reason="deterministic alignment found conflicting canonical IDs",
                    candidate_payload=dict(conflict),
                    source="entity_alignment",
                    evidence=str(conflict),
                    confidence=0.5,
                    scenario="shared",
                    relation_family="ALIGNMENT",
                    graph_impact="entity identity may affect many RCA paths",
                    recommended_action="review_merge",
                )
            )
    for edge in edges:
        priority, reason = _edge_priority(edge)
        if priority <= 0:
            continue
        items.append(
            ReviewQueueItem(
                target_key=edge.edge_id,
                item_type="edge",
                priority=priority,
                reason=reason,
                candidate_payload=edge.model_dump(),
                source=edge.source,
                evidence=edge.evidence,
                confidence=edge.confidence,
                scenario=edge.scenario,
                relation_family=edge.relation_family,
                graph_impact=_graph_impact(edge),
                recommended_action="accept_or_reject",
            )
        )
    return tuple(sorted(items, key=lambda item: (-item.priority, item.target_key)))


def review_queue_payload(items: tuple[ReviewQueueItem, ...]) -> list[dict[str, Any]]:
    """Return JSON-friendly review queue payload."""
    return [item.__dict__ for item in items]


def _edge_priority(edge: KGEdge) -> tuple[int, str]:
    if edge.review_status == "rejected":
        return 0, ""
    relation = edge.relation
    family = edge.relation_family
    source = edge.source.lower()
    if relation in {"CAUSES", "SUGGESTS_ROOT_CAUSE", "HAS_PLAUSIBLE_CAUSE"}:
        if "llm" in source or edge.confidence < 0.8:
            return 100, "causal/root-cause relation needs human confirmation"
        return 85, "causal/root-cause relation affects RCA reasoning"
    if edge.propagation_enabled and edge.confidence < 0.75:
        return 80, "low-confidence propagation edge affects RCA traversal"
    if family == "FAULT_SOURCE":
        return 78, "fault-source family participates in root-cause ranking"
    if relation == "ALIGNS_TO" and edge.confidence < 0.9:
        return 70, "alignment relation is not high confidence"
    if edge.review_status == "auto" and edge.propagation_enabled:
        return 65, "auto propagation edge should be sampled for review"
    if edge.review_status == "auto" and edge.confidence < 0.65:
        return 45, "low-confidence candidate edge"
    return 0, ""


def _graph_impact(edge: KGEdge) -> str:
    if edge.propagation_enabled:
        return "can change Top-K RCA propagation paths"
    if edge.relation == "ALIGNS_TO":
        return "can change entity linking and variable mapping"
    return "supporting semantic context"
