"""Draft KG intermediate representation for source-to-KG construction."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg_construction.candidate_entity_extractor import CandidateEntity
from kgtracevis.kg_construction.candidate_triple_extractor import CandidateTriple
from kgtracevis.kg_construction.confidence_assigner import edge_weight

DraftStatus = Literal["draft", "accepted", "rejected", "published"]

_REVIEW_STATUS_BY_DRAFT_STATUS = {
    "draft": "auto",
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
    aliases: tuple[str, ...] = ()
    description: str = ""
    evidence: str = ""
    evidence_span: str = ""
    confidence: float = 0.6
    status: DraftStatus = "draft"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_candidate_entity(self) -> CandidateEntity:
        """Convert the draft entity to the existing candidate entity contract."""
        evidence = self.evidence or self.evidence_span or self.draft_id
        return CandidateEntity(
            id=self.entity_id_suggestion,
            name=self.name,
            label=self.label,
            scenario=self.scenario,
            aliases=self.aliases,
            description=self.description,
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
        return CandidateTriple(
            head=self.head,
            relation=self.relation,
            tail=self.tail,
            scenario=self.scenario,
            source=self.source_id,
            evidence=self.evidence or self.evidence_span or self.draft_id,
            confidence=self.confidence,
            weight=edge_weight(self.confidence),
            review_status=_REVIEW_STATUS_BY_DRAFT_STATUS[self.status],
        )


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
