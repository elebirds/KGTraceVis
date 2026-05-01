"""Entity linking helpers."""

from __future__ import annotations

from typing import Any

from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence


def link_evidence_entities(
    evidence: Evidence,
    graph: KnowledgeGraph,
    *,
    top_k: int = 3,
    min_score: float = 0.55,
) -> list[dict[str, Any]]:
    """Link evidence fields to KG entities.

    The linker records ambiguity instead of silently forcing low-confidence
    matches. Downstream modules can choose how conservative they want to be.
    """
    links: list[dict[str, Any]] = []
    for field, mention in _iter_mentions(evidence):
        candidates = graph.candidates(
            mention,
            scenario=evidence.dataset,
            top_k=top_k,
            min_score=min_score,
        )
        if not candidates:
            links.append(
                {
                    "field": field,
                    "mention": mention,
                    "selected_entity_id": None,
                    "score": 0.0,
                    "match_type": "unmatched",
                    "ambiguous": False,
                    "candidates": [],
                }
            )
            continue
        selected = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        links.append(
            {
                "field": field,
                "mention": mention,
                "selected_entity_id": selected.entity_id,
                "score": round(selected.score, 4),
                "match_type": selected.match_type,
                "ambiguous": bool(second_score and selected.score - second_score < 0.08),
                "candidates": [candidate.model_dump() for candidate in candidates],
            }
        )
    return links


def selected_entities_by_field(linked_entities: list[dict[str, Any]]) -> dict[str, str]:
    """Return selected entity IDs keyed by field."""
    selected: dict[str, str] = {}
    for link in linked_entities:
        entity_id = link.get("selected_entity_id")
        if isinstance(entity_id, str):
            selected[str(link["field"])] = entity_id
    return selected


def _iter_mentions(evidence: Evidence) -> list[tuple[str, str]]:
    mentions: list[tuple[str, str]] = [
        ("object", evidence.object),
        ("anomaly_type", evidence.anomaly_type),
    ]
    if evidence.location:
        mentions.append(("location", evidence.location))
    if evidence.morphology:
        mentions.append(("morphology", evidence.morphology))
    for variable in evidence.raw_evidence.variables:
        mentions.append(("variable", variable))
    for event in evidence.raw_evidence.log_events:
        mentions.append(("log_event", event))
    return [(field, mention) for field, mention in mentions if mention]
