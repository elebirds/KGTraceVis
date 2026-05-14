"""Correction candidate generation helpers."""

from __future__ import annotations

from typing import Any

from kgtracevis.kg.consistency_checker import FIELD_RELATION_RULES
from kgtracevis.kg.entity_linker import selected_entities_by_field
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence


def generate_correction_candidates(
    evidence: Evidence,
    graph: KnowledgeGraph,
    linked_entities: list[dict[str, Any]],
    consistency: dict[str, Any],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Generate stable correction candidates from KG neighborhoods."""
    selected = selected_entities_by_field(linked_entities)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for check in consistency.get("checks", []):
        if check.get("passed"):
            continue
        source_field = str(check["source_field"])
        target_field = str(check["target_field"])
        source_id = selected.get(source_field)
        if not source_id:
            continue
        for relation in FIELD_RELATION_RULES.get((source_field, target_field), ()):
            for edge in graph.outgoing(source_id, relation, scenario=evidence.dataset):
                target = graph.nodes[edge.tail]
                key = (target_field, target.id)
                if key in seen:
                    continue
                seen.add(key)
                original_value = _field_value(evidence, target_field)
                candidates.append(
                    {
                        "candidate_id": _candidate_id(evidence.case_id, target_field, target.id),
                        "source_field": source_field,
                        "source_entity_id": source_id,
                        "target_field": target_field,
                        "field": target_field,
                        "original_value": original_value,
                        "original": original_value,
                        "suggested_entity_id": target.id,
                        "suggested_value": target.name,
                        "suggested": target.name,
                        "score": round(edge.confidence, 4),
                        "reason": f"{source_id} {relation} {target.id}",
                        "supporting_edge_ids": [edge.edge_id],
                        "supporting_edges": [edge.model_dump()],
                    }
                )

    candidates.sort(key=lambda item: (-float(item["score"]), str(item["candidate_id"])))
    return candidates[:top_k]


def _candidate_id(case_id: str, field: str, entity_id: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in entity_id)
    return f"corr_{case_id}_{field}_{normalized}"


def _field_value(evidence: Evidence, field: str) -> object:
    if field == "variable":
        return evidence.raw_evidence.variables
    if field == "log_event":
        return evidence.raw_evidence.log_events
    return getattr(evidence, field, None)
