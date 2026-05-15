"""Draft KG intermediate representation for source-to-KG construction."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.confidence_assigner import edge_weight

if TYPE_CHECKING:
    from kgtracevis.kg_construction.candidate_entity_extractor import CandidateEntity
    from kgtracevis.kg_construction.candidate_triple_extractor import CandidateTriple

DraftStatus = Literal["draft", "auto", "accepted", "rejected", "published"]

_REVIEW_STATUS_BY_DRAFT_STATUS = {
    "draft": "auto",
    "auto": "auto",
    "accepted": "reviewed",
    "rejected": "rejected",
    "published": "reviewed",
}


@dataclass(frozen=True)
class KGConstructionSource:
    """One source material record passed to construction extractors."""

    source_id: str
    source_type: str
    scenario: str = "shared"
    path: Path | None = None
    text: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DraftEntity:
    """A reviewable entity candidate before publication."""

    draft_id: str
    source_id: str
    extractor_name: str
    extractor_version: str
    scenario: str
    entity_id_suggestion: str
    name: str
    label: str
    canonical_id: str = ""
    aliases: tuple[str, ...] = ()
    description: str = ""
    evidence: str = ""
    evidence_span: str = ""
    confidence: float = 0.6
    status: DraftStatus = "draft"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_kg_node(self) -> KGNode:
        """Convert the draft entity directly to the KG node row contract."""
        return draft_entity_to_kg_node(self)

    def to_candidate_entity(self) -> CandidateEntity:
        """Convert the draft entity to the existing candidate entity contract."""
        from kgtracevis.kg_construction.candidate_entity_extractor import CandidateEntity

        node = self.to_kg_node()
        evidence = self.evidence or self.evidence_span or self.draft_id
        return CandidateEntity(
            id=node.id,
            name=node.name,
            label=node.label,
            scenario=node.scenario,
            aliases=node.aliases,
            description=node.description,
            source=self.source_id,
            evidence=evidence,
        )


@dataclass(frozen=True)
class DraftRelation:
    """A reviewable relation candidate before publication."""

    draft_id: str
    source_id: str
    extractor_name: str
    extractor_version: str
    scenario: str
    head: str
    relation: str
    tail: str
    evidence: str
    evidence_span: str = ""
    confidence: float = 0.6
    status: DraftStatus = "draft"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_candidate_triple(self) -> CandidateTriple:
        """Convert the draft relation to the existing candidate triple contract."""
        from kgtracevis.kg_construction.candidate_triple_extractor import CandidateTriple

        edge = self.to_kg_edge()
        return CandidateTriple(
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
            relation_family=edge.relation_family,
            propagation_enabled=edge.propagation_enabled,
            propagation_direction=edge.propagation_direction,
            propagation_priority=edge.propagation_priority,
            attenuation=edge.attenuation,
            edge_weight=edge.edge_weight,
            root_candidate=edge.root_candidate,
            observable=edge.observable,
            event_anchor=edge.event_anchor,
            fault_anchor=edge.fault_anchor,
            task_view=edge.task_view,
            confidence_policy=edge.confidence_policy,
            external_edge_id=edge.external_edge_id,
            kg_build_id=edge.kg_build_id,
        )

    def to_kg_edge(self) -> KGEdge:
        """Convert the draft relation to the extended KG edge contract."""
        return draft_relation_to_kg_edge(self)


@dataclass(frozen=True)
class DraftKG:
    """Draft entities and relations emitted by one or more extractors."""

    entities: tuple[DraftEntity, ...] = ()
    relations: tuple[DraftRelation, ...] = ()

    @classmethod
    def combine(cls, drafts: Sequence[DraftKG]) -> DraftKG:
        """Combine multiple draft outputs while preserving extractor order."""
        return cls(
            entities=tuple(entity for draft in drafts for entity in draft.entities),
            relations=tuple(relation for draft in drafts for relation in draft.relations),
        )


def draft_status_to_review_status(status: DraftStatus) -> str:
    """Return the KG edge review status corresponding to a draft status."""
    return _REVIEW_STATUS_BY_DRAFT_STATUS[status]


def draft_entity_to_kg_node(entity: DraftEntity) -> KGNode:
    """Convert a draft entity directly to a KG node row."""
    return KGNode(
        id=entity.canonical_id or entity.entity_id_suggestion,
        name=entity.name,
        label=entity.label,
        scenario=entity.scenario,
        aliases=entity.aliases,
        description=entity.description,
    )


def draft_relation_to_kg_edge(relation: DraftRelation) -> KGEdge:
    """Convert a draft relation directly to a KG edge row with RCA metadata."""
    return KGEdge(
        head=relation.head,
        relation=relation.relation,
        tail=relation.tail,
        scenario=relation.scenario,
        source=relation.source_id,
        evidence=relation.evidence or relation.evidence_span or relation.draft_id,
        confidence=relation.confidence,
        weight=edge_weight(relation.confidence),
        review_status=draft_status_to_review_status(relation.status),
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
        relation_family=_metadata_text(relation.metadata, "relation_family"),
        propagation_enabled=_metadata_bool(relation.metadata, "propagation_enabled", False),
        propagation_direction=_metadata_text(
            relation.metadata,
            "propagation_direction",
            default="forward",
        ),
        propagation_priority=_metadata_float(relation.metadata, "propagation_priority", 0.0),
        attenuation=_metadata_float(relation.metadata, "attenuation", 1.0),
        edge_weight=_metadata_optional_float(relation.metadata, "edge_weight"),
        root_candidate=_metadata_bool(relation.metadata, "root_candidate", False),
        observable=_metadata_bool(relation.metadata, "observable", False),
        event_anchor=_metadata_text(relation.metadata, "event_anchor"),
        fault_anchor=_metadata_text(relation.metadata, "fault_anchor"),
        task_view=_metadata_text(relation.metadata, "task_view"),
        confidence_policy=_metadata_text(relation.metadata, "confidence_policy"),
        external_edge_id=_metadata_text(relation.metadata, "external_edge_id"),
        kg_build_id=_metadata_text(relation.metadata, "kg_build_id"),
    )


def _metadata_text(
    metadata: Mapping[str, Any],
    key: str,
    *,
    default: str = "",
) -> str:
    value = metadata.get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _metadata_bool(metadata: Mapping[str, Any], key: str, default: bool) -> bool:
    value = metadata.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _metadata_float(metadata: Mapping[str, Any], key: str, default: float) -> float:
    value = _metadata_optional_float(metadata, key)
    return default if value is None else value


def _metadata_optional_float(metadata: Mapping[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def draft_relations_from_source_text(
    *,
    source_id: str,
    source_text: str,
    extractor_name: str,
    extractor_version: str,
    default_scenario: str = "shared",
    confidence: float = 0.55,
) -> tuple[DraftRelation, ...]:
    """Parse simple CSV-like source text into reviewable relation drafts.

    Each non-comment line is expected to contain at least
    `head,relation,tail`, with optional `scenario,evidence` columns.
    """
    relations: list[DraftRelation] = []
    for line_number, line in enumerate(source_text.splitlines(), start=1):
        relation = _draft_relation_from_line(
            line,
            line_number=line_number,
            source_id=source_id,
            extractor_name=extractor_name,
            extractor_version=extractor_version,
            default_scenario=default_scenario,
            confidence=confidence,
        )
        if relation is not None:
            relations.append(relation)
    return tuple(relations)


def _draft_relation_from_line(
    line: str,
    *,
    line_number: int,
    source_id: str,
    extractor_name: str,
    extractor_version: str,
    default_scenario: str,
    confidence: float,
) -> DraftRelation | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    row = next(csv.reader(StringIO(stripped)))
    if len(row) < 3:
        return None
    head = row[0].strip()
    relation = row[1].strip()
    tail = row[2].strip()
    scenario = row[3].strip() if len(row) >= 4 and row[3].strip() else default_scenario
    evidence = row[4].strip() if len(row) >= 5 and row[4].strip() else stripped
    if not head or not relation or not tail or not scenario:
        return None
    return DraftRelation(
        draft_id=f"{source_id}:relation:{line_number}",
        source_id=source_id,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        scenario=scenario,
        head=head,
        relation=relation,
        tail=tail,
        evidence=evidence,
        confidence=confidence,
        metadata={"source_line": line_number},
    )
