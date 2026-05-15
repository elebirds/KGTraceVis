"""Candidate triple extraction utilities."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kgtracevis.kg.graph import KGEdge
from kgtracevis.kg_construction.confidence_assigner import assign_confidence, edge_weight


@dataclass(frozen=True)
class CandidateTriple:
    """A source-constrained candidate KG edge."""

    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float
    weight: float
    review_status: str = "auto"
    feedback_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    relation_family: str = ""
    propagation_enabled: bool = False
    propagation_direction: str = "forward"
    propagation_priority: float = 0.0
    attenuation: float = 1.0
    edge_weight: float | None = None
    root_candidate: bool = False
    observable: bool = False
    event_anchor: str = ""
    fault_anchor: str = ""
    task_view: str = ""
    confidence_policy: str = ""
    external_edge_id: str = ""
    kg_build_id: str = ""

    def to_kg_edge(self) -> KGEdge:
        """Convert the candidate to the KG edge CSV contract."""
        return KGEdge(
            head=self.head,
            relation=self.relation,
            tail=self.tail,
            scenario=self.scenario,
            source=self.source,
            evidence=self.evidence,
            confidence=self.confidence,
            weight=self.weight,
            review_status=self.review_status,
            feedback_count=self.feedback_count,
            accepted_count=self.accepted_count,
            rejected_count=self.rejected_count,
            relation_family=self.relation_family,
            propagation_enabled=self.propagation_enabled,
            propagation_direction=self.propagation_direction,
            propagation_priority=self.propagation_priority,
            attenuation=self.attenuation,
            edge_weight=self.edge_weight,
            root_candidate=self.root_candidate,
            observable=self.observable,
            event_anchor=self.event_anchor,
            fault_anchor=self.fault_anchor,
            task_view=self.task_view,
            confidence_policy=self.confidence_policy,
            external_edge_id=self.external_edge_id,
            kg_build_id=self.kg_build_id,
        )


def extract_candidate_triples(
    records: Iterable[Mapping[str, Any]],
    *,
    source_id: str = "",
    source_type: str = "",
) -> list[CandidateTriple]:
    """Extract candidate triples from structured records only."""
    triples: list[CandidateTriple] = []
    for record in records:
        triple = _triple_from_record(record, source_id=source_id, source_type=source_type)
        if triple is not None:
            triples.append(triple)
    return triples


def _triple_from_record(
    record: Mapping[str, Any],
    *,
    source_id: str,
    source_type: str,
) -> CandidateTriple | None:
    head = _string_value(record, "head", "subject", "source_node")
    relation = _string_value(record, "relation", "predicate", "edge_type")
    tail = _string_value(record, "tail", "object", "target_node")
    scenario = _string_value(record, "scenario")

    if not any((head, relation, tail, scenario)):
        return None
    missing = [
        field
        for field, value in {
            "head/subject/source_node": head,
            "relation/predicate/edge_type": relation,
            "tail/object/target_node": tail,
            "scenario": scenario,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"candidate triple missing required fields: {', '.join(missing)}")

    explicit_confidence = _optional_float(record.get("confidence"))
    resolved_source_type = _string_value(record, "source_type", "type") or source_type
    confidence = assign_confidence(resolved_source_type, explicit_confidence=explicit_confidence)
    weight = _optional_float(record.get("weight"))
    source = _string_value(record, "source", "source_id") or source_id
    if not source:
        raise ValueError("candidate triple missing required source/source_id")
    return CandidateTriple(
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        source=source,
        evidence=_string_value(record, "evidence") or _compact_json(record),
        confidence=confidence,
        weight=edge_weight(confidence) if weight is None else weight,
        review_status=_string_value(record, "review_status") or "auto",
        feedback_count=_int_value(record.get("feedback_count")),
        accepted_count=_int_value(record.get("accepted_count")),
        rejected_count=_int_value(record.get("rejected_count")),
    )


def _string_value(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _int_value(value: object) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    return int(text)


def _compact_json(record: Mapping[str, Any]) -> str:
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":"))
