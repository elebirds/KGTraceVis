"""KG consistency checking helpers."""

from __future__ import annotations

from typing import Any

from kgtracevis.kg.entity_linker import selected_entities_by_field
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence

FIELD_RELATION_RULES = {
    ("anomaly_type", "morphology"): ("HAS_MORPHOLOGY",),
    ("anomaly_type", "location"): ("OCCURS_ON", "HAS_LOCATION"),
    ("variable", "location"): ("MEASURED_IN", "BELONGS_TO_UNIT"),
    ("anomaly_type", "log_event"): ("ASSOCIATED_WITH_EVENT",),
}


def check_consistency(
    evidence: Evidence,
    graph: KnowledgeGraph,
    linked_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check field-level consistency against KG relations."""
    selected = selected_entities_by_field(linked_entities)
    checks: list[dict[str, Any]] = []
    inconsistent_fields: set[str] = set()

    linked_count = sum(1 for link in linked_entities if link.get("selected_entity_id"))
    entity_score = linked_count / len(linked_entities) if linked_entities else 1.0

    for (source_field, target_field), relations in FIELD_RELATION_RULES.items():
        source_id = selected.get(source_field)
        target_id = selected.get(target_field)
        if not source_id or not target_id:
            continue
        matched_relation = _first_matching_relation(graph, source_id, target_id, relations)
        passed = matched_relation is not None
        if not passed:
            inconsistent_fields.update({source_field, target_field})
        checks.append(
            {
                "source_field": source_field,
                "target_field": target_field,
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relations": list(relations),
                "passed": passed,
                "matched_relation": matched_relation,
            }
        )

    relation_score = (
        sum(1 for check in checks if check["passed"]) / len(checks) if checks else 1.0
    )
    consistency_score = 0.4 * entity_score + 0.6 * relation_score
    return {
        "consistency_score": round(consistency_score, 4),
        "inconsistent_fields": sorted(inconsistent_fields),
        "checks": checks,
    }


def _first_matching_relation(
    graph: KnowledgeGraph,
    source_id: str,
    target_id: str,
    relations: tuple[str, ...],
) -> str | None:
    for relation in relations:
        if graph.has_edge(source_id, relation, target_id):
            return relation
    return None
