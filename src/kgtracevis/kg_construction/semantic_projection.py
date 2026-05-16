"""Semantic layer projection from aligned DraftKG."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.draft import DraftKG, DraftRelation
from kgtracevis.kg_construction.profiles import RcaProfile, SemanticDerivedRelationRule
from kgtracevis.kg_construction.triple_cleaner import (
    clean_kg_edges,
    clean_kg_nodes,
)


@dataclass(frozen=True)
class SemanticLayerResult:
    """Semantic layer rows and manifest data."""

    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    manifest: dict[str, object]


def project_semantic_layer(draft: DraftKG, profile: RcaProfile) -> SemanticLayerResult:
    """Project aligned draft knowledge into a task-relevant semantic layer."""
    entity_rows = [
        entity.to_kg_node()
        for entity in draft.entities
        if entity.label in profile.keep_labels
    ]
    nodes = tuple(clean_kg_nodes(entity_rows))
    node_labels = {node.id: node.label for node in nodes}
    node_ids = set(node_labels)
    relation_rows: list[KGEdge] = []
    skipped_relations: list[str] = []
    label_constraint_skipped_relations: list[str] = []
    for relation in draft.relations:
        projected = _project_relation(relation, profile=profile)
        if projected.relation not in profile.relation_whitelist:
            skipped_relations.append(relation.draft_id)
            continue
        edge = projected.to_kg_edge()
        if edge.head not in node_ids or edge.tail not in node_ids:
            skipped_relations.append(relation.draft_id)
            continue
        if not profile.relation_endpoints_allowed(
            edge.relation,
            head_label=node_labels[edge.head],
            tail_label=node_labels[edge.tail],
        ):
            skipped_relations.append(relation.draft_id)
            label_constraint_skipped_relations.append(relation.draft_id)
            continue
        relation_rows.append(edge)
    base_edges = tuple(clean_kg_edges(relation_rows))
    derived_edges = _derive_semantic_edges(base_edges, profile=profile)
    edges = tuple(clean_kg_edges((*base_edges, *derived_edges)))
    manifest = {
        "artifact_type": "semantic_layer_manifest_v1",
        "profile": profile.domain_id,
        "scenario": profile.scenario,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "kept_labels": sorted({node.label for node in nodes}),
        "relation_families": sorted(
            {edge.relation_family for edge in edges if edge.relation_family}
        ),
        "skipped_relation_count": len(skipped_relations),
        "skipped_relation_ids": skipped_relations[:100],
        "label_constraint_skipped_relation_count": len(
            label_constraint_skipped_relations
        ),
        "label_constraint_skipped_relation_ids": label_constraint_skipped_relations[:100],
        "derived_edge_count": len(derived_edges),
        "derived_edge_ids": [edge.edge_id for edge in derived_edges[:100]],
    }
    return SemanticLayerResult(nodes=nodes, edges=edges, manifest=manifest)


def _project_relation(relation: DraftRelation, *, profile: RcaProfile) -> DraftRelation:
    projection_rule = profile.projection_rule_for(relation.relation)
    rewritten = projection_rule.normalized_target()
    family = profile.relation_family_for(
        rewritten,
        explicit=str(relation.metadata.get("relation_family") or ""),
    )
    head = relation.tail if projection_rule.swap_endpoints else relation.head
    tail = relation.head if projection_rule.swap_endpoints else relation.tail
    metadata = dict(relation.metadata)
    metadata["relation_family"] = family
    metadata["projection_source_relation"] = relation.relation.strip().upper()
    metadata["projection_target_relation"] = rewritten
    if projection_rule.swap_endpoints:
        metadata["projection_swapped_endpoints"] = True
    propagation_enabled = _optional_bool(relation.metadata.get("propagation_enabled"))
    metadata["propagation_enabled"] = (
        propagation_enabled
        if propagation_enabled is not None
        else profile.propagation_enabled_for(family)
    )
    propagation_direction = str(relation.metadata.get("propagation_direction") or "").strip()
    metadata["propagation_direction"] = (
        propagation_direction.lower()
        if propagation_direction
        else profile.propagation_direction_for(family)
    )
    propagation_priority = _optional_float(relation.metadata.get("propagation_priority"))
    metadata["propagation_priority"] = profile.propagation_priority_for(
        family,
        explicit=propagation_priority,
    )
    attenuation = _optional_float(relation.metadata.get("attenuation"))
    metadata["attenuation"] = profile.attenuation_for(
        family,
        explicit=attenuation,
    )
    explicit_edge_weight = _optional_float(relation.metadata.get("edge_weight"))
    metadata["edge_weight"] = profile.edge_weight_for(
        family,
        base_weight=edge_weight(relation.confidence),
        explicit=explicit_edge_weight,
    )
    return replace(relation, head=head, relation=rewritten, tail=tail, metadata=metadata)


def _derive_semantic_edges(
    edges: tuple[KGEdge, ...],
    *,
    profile: RcaProfile,
) -> tuple[KGEdge, ...]:
    existing_ids = {edge.edge_id for edge in edges}
    derived: list[KGEdge] = []
    for rule in profile.semantic_derived_relation_rules:
        if rule.normalized_target() not in profile.relation_whitelist:
            continue
        derived.extend(
            _derive_edges_for_rule(
                edges,
                rule=rule,
                profile=profile,
                existing_ids=existing_ids | {edge.edge_id for edge in derived},
            )
        )
    return tuple(derived)


def _derive_edges_for_rule(
    edges: tuple[KGEdge, ...],
    *,
    rule: SemanticDerivedRelationRule,
    profile: RcaProfile,
    existing_ids: set[str],
) -> tuple[KGEdge, ...]:
    left_edges = [
        edge for edge in edges if edge.relation == rule.normalized_left()
    ]
    right_edges = [
        edge for edge in edges if edge.relation == rule.normalized_right()
    ]
    derived: list[KGEdge] = []
    target_relation = rule.normalized_target()
    family = rule.relation_family.strip().upper() or profile.relation_family_for(
        target_relation
    )
    for left in left_edges:
        for right in right_edges:
            if left.scenario != right.scenario or left.tail != right.head:
                continue
            confidence = _derived_confidence(left, right, rule)
            candidate = KGEdge(
                head=left.head,
                relation=target_relation,
                tail=right.tail,
                scenario=left.scenario,
                source=f"semantic_projection:{rule.rule_id}",
                evidence=(
                    f"Derived by semantic projection rule {rule.rule_id} from "
                    f"{left.edge_id} and {right.edge_id}. "
                    f"left evidence: {left.evidence}; right evidence: {right.evidence}"
                ),
                confidence=confidence,
                weight=edge_weight(confidence),
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
                relation_family=family,
                propagation_enabled=profile.propagation_enabled_for(family),
                propagation_direction=profile.propagation_direction_for(family),
                propagation_priority=profile.propagation_priority_for(family),
                attenuation=profile.attenuation_for(family),
                edge_weight=profile.edge_weight_for(
                    family,
                    base_weight=edge_weight(confidence),
                ),
                external_edge_id=(
                    f"derived:{rule.rule_id}:{left.edge_id}:{right.edge_id}"
                ),
            )
            if candidate.edge_id in existing_ids:
                continue
            existing_ids.add(candidate.edge_id)
            derived.append(candidate)
    return tuple(derived)


def _derived_confidence(
    left: KGEdge,
    right: KGEdge,
    rule: SemanticDerivedRelationRule,
) -> float:
    if rule.confidence_policy == "average":
        return (left.confidence + right.confidence) / 2.0
    if rule.confidence_policy == "product":
        return left.confidence * right.confidence
    return min(left.confidence, right.confidence)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if not text:
        return None
    return text.lower() in {"1", "true", "yes", "y"}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)
