"""Entity linking helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence

LINKABLE_OBSERVATION_FACETS = {
    "object",
    "anomaly_type",
    "location",
    "morphology",
    "variable",
    "log_event",
}
FIELD_ALLOWED_LABELS = {
    "object": {"Object"},
    "anomaly_type": {"Anomaly", "Defect", "Fault", "Pattern"},
    "location": {"Location", "ProcessUnit"},
    "morphology": {"Morphology", "Pattern"},
    "variable": {"Variable"},
    "log_event": {"EvidenceSource"},
}


@dataclass(frozen=True)
class EvidenceMention:
    """A text mention from a canonical observation or compatibility fallback."""

    field: str
    mention: str
    obs_id: str | None = None
    facet: str | None = None


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
    occurrences: dict[tuple[str, str], int] = {}
    for mention_item in _iter_mentions(evidence):
        occurrence_key = (mention_item.field, mention_item.mention)
        occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
        link_id = _link_id(
            evidence.case_id,
            mention_item.field,
            mention_item.mention,
            occurrences[occurrence_key],
        )
        raw_candidates = graph.candidates(
            mention_item.mention,
            scenario=evidence.dataset,
            top_k=max(top_k * 5, 10),
            min_score=min_score,
        )
        candidates = _field_aware_candidates(
            mention_item.field,
            raw_candidates,
            graph,
            top_k=top_k,
        )
        if not candidates:
            links.append(_link_payload(mention_item, link_id, candidates=[]))
            continue
        selected = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        ambiguity_margin = (
            round(selected.score - second_score, 4) if second_score else None
        )
        links.append(
            _link_payload(
                mention_item,
                link_id,
                selected_entity_id=selected.entity_id,
                score=round(selected.score, 4),
                match_type=selected.match_type,
                ambiguous=bool(
                    ambiguity_margin is not None and ambiguity_margin < 0.08
                ),
                ambiguity_margin=ambiguity_margin,
                candidates=[candidate.model_dump() for candidate in candidates],
            )
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


def _field_aware_candidates(
    field: str,
    candidates: list[Any],
    graph: KnowledgeGraph,
    *,
    top_k: int,
) -> list[Any]:
    """Return only candidates whose node labels match the evidence field."""
    allowed_labels = FIELD_ALLOWED_LABELS.get(field)
    if not allowed_labels:
        return candidates[:top_k]
    filtered = [
        candidate
        for candidate in candidates
        if graph.nodes.get(candidate.entity_id) is not None
        and graph.nodes[candidate.entity_id].label in allowed_labels
    ]
    return filtered[:top_k]


def _link_payload(
    mention: EvidenceMention,
    link_id: str,
    *,
    candidates: list[dict[str, Any]],
    selected_entity_id: str | None = None,
    score: float = 0.0,
    match_type: str = "unmatched",
    ambiguous: bool = False,
    ambiguity_margin: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "link_id": link_id,
        "field": mention.field,
        "mention": mention.mention,
        "selected_entity_id": selected_entity_id,
        "score": score,
        "match_type": match_type,
        "ambiguous": ambiguous,
        "ambiguity_margin": ambiguity_margin,
        "candidates": candidates,
    }
    if mention.obs_id is not None:
        payload["obs_id"] = mention.obs_id
    if mention.facet is not None:
        payload["facet"] = mention.facet
    return payload


def _iter_mentions(evidence: Evidence) -> list[EvidenceMention]:
    mentions: list[EvidenceMention] = []
    seen: set[tuple[str, str]] = set()
    observation_facets: set[str] = set()
    for observation in evidence.observations:
        facet = observation.facet
        mention = observation.name.strip()
        if facet not in LINKABLE_OBSERVATION_FACETS or not mention:
            continue
        item = EvidenceMention(
            field=facet,
            mention=mention,
            obs_id=observation.obs_id,
            facet=facet,
        )
        mentions.append(item)
        seen.add((item.field, item.mention))
        observation_facets.add(item.field)

    fallback_mentions: list[tuple[str, str]] = [
        ("object", evidence.object),
        ("anomaly_type", evidence.anomaly_type),
    ]
    if evidence.location:
        fallback_mentions.append(("location", evidence.location))
    if evidence.morphology:
        fallback_mentions.append(("morphology", evidence.morphology))
    for variable in evidence.raw_evidence.variables:
        fallback_mentions.append(("variable", variable))
    for event in evidence.raw_evidence.log_events:
        fallback_mentions.append(("log_event", event))

    for field, mention in fallback_mentions:
        if field in observation_facets:
            continue
        if mention and (field, mention) not in seen:
            mentions.append(EvidenceMention(field=field, mention=mention))
    return mentions


def _link_id(case_id: str, field: str, mention: str, occurrence: int) -> str:
    mention_token = _stable_token(mention) or "unknown"
    base = f"link_{case_id}_{field}_{mention_token}"
    if occurrence > 1:
        return f"{base}_{occurrence:02d}"
    return base


def _stable_token(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
