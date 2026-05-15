"""RCA reasoning view construction from a semantic layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.profiles import RcaProfile, RelationFamilyPolicy


@dataclass(frozen=True)
class RcaReasoningView:
    """Task-specific RCA graph view used by reasoning algorithms."""

    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    manifest: dict[str, object]


@dataclass(frozen=True)
class RcaEdgeScore:
    """Deterministic profile-derived RCA edge score components."""

    source_trust: float
    score: float
    confidence_component: float
    priority_component: float
    attenuation_component: float
    source_trust_component: float


def build_rca_reasoning_view(
    nodes: tuple[KGNode, ...],
    edges: tuple[KGEdge, ...],
    *,
    profile: RcaProfile,
    kg_build_id: str,
) -> RcaReasoningView:
    """Annotate semantic rows for task-specific RCA propagation."""
    observable_ids = {node.id for node in nodes if node.label in profile.observable_labels}
    root_candidate_ids = {
        node.id for node in nodes if node.label in profile.root_candidate_labels
    }
    rca_edges = tuple(
        _annotate_edge(
            edge,
            profile=profile,
            kg_build_id=kg_build_id,
            observable_ids=observable_ids,
            root_candidate_ids=root_candidate_ids,
        )
        for edge in edges
    )
    relation_families = sorted(
        {edge.relation_family for edge in rca_edges if edge.relation_family}
    )
    manifest = {
        "artifact_type": "rca_view_manifest_v1",
        "profile": profile.domain_id,
        "scenario": profile.scenario,
        "task_view": profile.task_view,
        "kg_build_id": kg_build_id,
        "node_count": len(nodes),
        "edge_count": len(rca_edges),
        "propagation_edge_count": sum(edge.propagation_enabled for edge in rca_edges),
        "root_candidate_count": len(root_candidate_ids),
        "observable_count": len(observable_ids),
        "relation_families": relation_families,
        "relation_family_policies": {
            family: asdict(profile.relation_family_policy_for(family))
            for family in relation_families
        },
        "score_summary": _score_summary(rca_edges),
    }
    return RcaReasoningView(nodes=nodes, edges=rca_edges, manifest=manifest)


def _annotate_edge(
    edge: KGEdge,
    *,
    profile: RcaProfile,
    kg_build_id: str,
    observable_ids: set[str],
    root_candidate_ids: set[str],
) -> KGEdge:
    family = edge.relation_family or profile.relation_family_for(edge.relation)
    propagation_enabled = profile.propagation_enabled_for(
        family,
        explicit=edge.propagation_enabled,
    )
    propagation_direction = profile.propagation_direction_for(
        family,
        explicit=edge.propagation_direction if edge.propagation_direction != "forward" else "",
    )
    propagation_priority = profile.propagation_priority_for(
        family,
        explicit=edge.propagation_priority if edge.propagation_priority else None,
    )
    attenuation = profile.attenuation_for(
        family,
        explicit=edge.attenuation if edge.attenuation != 1.0 else None,
    )
    edge_weight = profile.edge_weight_for(
        family,
        base_weight=edge.weight,
        explicit=edge.edge_weight,
    )
    scoring = _score_edge(
        confidence=edge.confidence,
        propagation_priority=propagation_priority if propagation_enabled else 0.0,
        attenuation=attenuation,
        review_status=edge.review_status,
        policy=profile.relation_family_policy_for(family),
    )
    return KGEdge(
        head=edge.head,
        relation=edge.relation,
        tail=edge.tail,
        scenario=edge.scenario,
        source=edge.source,
        evidence=edge.evidence,
        confidence=edge.confidence,
        weight=edge.weight,
        review_status=edge.review_status,
        feedback_count=edge.feedback_count,
        accepted_count=edge.accepted_count,
        rejected_count=edge.rejected_count,
        relation_family=family,
        propagation_enabled=propagation_enabled,
        propagation_direction=propagation_direction,
        propagation_priority=propagation_priority if propagation_enabled else 0.0,
        attenuation=attenuation,
        edge_weight=edge_weight,
        root_candidate=edge.root_candidate or edge.head in root_candidate_ids,
        observable=edge.observable or edge.tail in observable_ids,
        event_anchor=edge.event_anchor,
        fault_anchor=edge.fault_anchor,
        task_view=edge.task_view or profile.task_view,
        confidence_policy=edge.confidence_policy or profile.confidence_policy,
        source_trust=scoring.source_trust,
        rca_score=scoring.score,
        rca_score_confidence=scoring.confidence_component,
        rca_score_priority=scoring.priority_component,
        rca_score_attenuation=scoring.attenuation_component,
        rca_score_source_trust=scoring.source_trust_component,
        external_edge_id=edge.external_edge_id,
        kg_build_id=edge.kg_build_id or kg_build_id,
    )


def _score_edge(
    *,
    confidence: float,
    propagation_priority: float,
    attenuation: float,
    review_status: str,
    policy: RelationFamilyPolicy,
) -> RcaEdgeScore:
    source_trust = _clamp01(policy.source_trust_for(review_status))
    components = {
        "confidence": _clamp01(confidence),
        "priority": _clamp01(propagation_priority),
        "attenuation": _clamp01(attenuation),
        "source_trust": source_trust,
    }
    weights = {
        "confidence": max(0.0, policy.confidence_score_weight),
        "priority": max(0.0, policy.priority_score_weight),
        "attenuation": max(0.0, policy.attenuation_score_weight),
        "source_trust": max(0.0, policy.source_trust_score_weight),
    }
    normalizer = sum(weights.values()) or 1.0
    weighted = {
        key: components[key] * weights[key] / normalizer
        for key in components
    }
    score = _clamp01(sum(weighted.values()))
    return RcaEdgeScore(
        source_trust=source_trust,
        score=score,
        confidence_component=weighted["confidence"],
        priority_component=weighted["priority"],
        attenuation_component=weighted["attenuation"],
        source_trust_component=weighted["source_trust"],
    )


def _score_summary(edges: tuple[KGEdge, ...]) -> dict[str, object]:
    scores = [edge.rca_score for edge in edges]
    propagation_scores = [
        edge.rca_score for edge in edges if edge.propagation_enabled
    ]
    return {
        "edge_score_count": len(scores),
        "propagation_score_count": len(propagation_scores),
        "min_rca_score": min(scores) if scores else 0.0,
        "max_rca_score": max(scores) if scores else 0.0,
        "mean_rca_score": sum(scores) / len(scores) if scores else 0.0,
        "mean_propagation_rca_score": (
            sum(propagation_scores) / len(propagation_scores)
            if propagation_scores
            else 0.0
        ),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
