"""Semantic layer projection from aligned DraftKG."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.draft import DraftKG, DraftRelation
from kgtracevis.kg_construction.profiles import RcaProfile
from kgtracevis.kg_construction.triple_cleaner import (
    clean_candidate_nodes,
    clean_candidate_triples,
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
        entity.to_candidate_entity()
        for entity in draft.entities
        if entity.label in profile.keep_labels
    ]
    nodes = tuple(clean_candidate_nodes(entity_rows))
    node_ids = {node.id for node in nodes}
    relation_rows: list[KGEdge] = []
    skipped_relations: list[str] = []
    for relation in draft.relations:
        projected = _project_relation(relation, profile=profile)
        if projected.relation not in profile.relation_whitelist:
            skipped_relations.append(relation.draft_id)
            continue
        edge = projected.to_kg_edge()
        if edge.head not in node_ids or edge.tail not in node_ids:
            skipped_relations.append(relation.draft_id)
            continue
        relation_rows.append(edge)
    edges = tuple(clean_candidate_triples(relation_rows))
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
    }
    return SemanticLayerResult(nodes=nodes, edges=edges, manifest=manifest)


def _project_relation(relation: DraftRelation, *, profile: RcaProfile) -> DraftRelation:
    rewritten = profile.rewrite_relation(relation.relation)
    family = profile.relation_family_for(
        rewritten,
        explicit=str(relation.metadata.get("relation_family") or ""),
    )
    metadata = dict(relation.metadata)
    metadata["relation_family"] = family
    metadata.setdefault(
        "propagation_enabled",
        profile.propagation_enabled_for(
            family,
            explicit=_optional_bool(relation.metadata.get("propagation_enabled")),
        ),
    )
    return replace(relation, relation=rewritten, metadata=metadata)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if not text:
        return None
    return text.lower() in {"1", "true", "yes", "y"}
