"""RCA reasoning view construction from a semantic layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.profiles import RcaProfile


@dataclass(frozen=True)
class RcaReasoningView:
    """Task-specific RCA graph view used by reasoning algorithms."""

    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    manifest: dict[str, object]


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
        external_edge_id=edge.external_edge_id,
        kg_build_id=edge.kg_build_id or kg_build_id,
    )
