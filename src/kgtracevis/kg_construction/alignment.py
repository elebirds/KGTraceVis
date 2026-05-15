"""Deterministic entity alignment for DraftKG candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from kgtracevis.kg.graph import normalize_text
from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    draft_status_to_review_status,
)
from kgtracevis.kg_construction.models import KGConstructionReviewDecision
from kgtracevis.kg_construction.profiles import RcaProfile


@dataclass(frozen=True)
class AlignmentCandidate:
    """One deterministic alignment decision or unresolved conflict."""

    source_entity_id: str
    canonical_id: str
    match_type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class CanonicalEntityEntry:
    """One canonical entity table row emitted by deterministic alignment."""

    canonical_id: str
    name: str
    label: str
    scenario: str
    source_entity_ids: tuple[str, ...]
    draft_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    aliases: tuple[str, ...]
    external_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class AlignmentIssueRecord:
    """Stable manifest row for unresolved entities and alignment conflicts."""

    issue_id: str
    issue_type: str
    source_entity_id: str
    canonical_id: str
    reason: str
    scenario: str
    source_id: str
    evidence: str
    confidence: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class AlignmentResult:
    """Output of the entity alignment stage."""

    draft: DraftKG
    alignment_relations: tuple[DraftRelation, ...]
    canonical_entities: tuple[CanonicalEntityEntry, ...]
    merge_candidates: tuple[AlignmentCandidate, ...]
    unresolved_entities: tuple[DraftEntity, ...]
    unresolved_records: tuple[AlignmentIssueRecord, ...]
    conflicts: tuple[dict[str, object], ...]
    conflict_records: tuple[AlignmentIssueRecord, ...]

    def manifest(self) -> dict[str, object]:
        """Return a JSON-friendly alignment manifest."""
        return {
            "artifact_type": "entity_alignment_manifest_v1",
            "aligned_entity_count": len(self.draft.entities),
            "canonical_entity_count": len(self.canonical_entities),
            "alignment_relation_count": len(self.alignment_relations),
            "merge_candidate_count": len(self.merge_candidates),
            "unresolved_entity_count": len(self.unresolved_entities),
            "conflict_count": len(self.conflicts),
            "canonical_entities": [
                _jsonable(asdict(entry)) for entry in self.canonical_entities
            ],
            "alignment_relations": [
                _jsonable(_alignment_relation_payload(relation))
                for relation in self.alignment_relations
            ],
            "merge_candidates": [
                _jsonable(asdict(candidate)) for candidate in self.merge_candidates
            ],
            "unresolved_entities": [
                _jsonable(asdict(record)) for record in self.unresolved_records
            ],
            "conflicts": [
                _jsonable(asdict(record)) for record in self.conflict_records
            ],
        }


def run_entity_alignment(
    draft: DraftKG,
    profile: RcaProfile,
    *,
    review_decisions: tuple[KGConstructionReviewDecision, ...] = (),
) -> AlignmentResult:
    """Apply deterministic ID, alias, external-id, and signal mapping alignment."""
    canonical_by_identity: dict[str, str] = {}
    candidates: list[AlignmentCandidate] = []
    conflicts: list[dict[str, object]] = []
    aligned_entities: list[DraftEntity] = []
    alignment_relations: list[DraftRelation] = []
    endpoint_map: dict[str, str] = {}
    unresolved_records: list[AlignmentIssueRecord] = []
    conflict_records: list[AlignmentIssueRecord] = []
    canonical_overrides, split_overrides = _alignment_review_overrides(review_decisions)

    for entity in draft.entities:
        suggested = entity.canonical_id or entity.entity_id_suggestion
        canonical_id = suggested
        match_type = "exact_id"
        entity_key = entity.entity_id_suggestion or entity.draft_id
        reviewed_override = canonical_overrides.get(entity_key)
        reviewed_split = entity_key in split_overrides
        if reviewed_override:
            canonical_id = reviewed_override
            match_type = "reviewed_override"
        elif reviewed_split:
            canonical_id = suggested or entity.entity_id_suggestion or entity.draft_id
            match_type = "reviewed_split"
        else:
            for identity in _entity_identities(entity):
                existing = canonical_by_identity.get(identity)
                if existing is None:
                    continue
                canonical_id = existing
                match_type = "alias"
                if existing != suggested:
                    candidates.append(
                        AlignmentCandidate(
                            source_entity_id=entity.entity_id_suggestion,
                            canonical_id=existing,
                            match_type=match_type,
                            confidence=0.95,
                            reason=f"deterministic {match_type} match in {profile.domain_id}",
                        )
                    )
                break
        metadata = dict(entity.metadata)
        if match_type.startswith("reviewed_"):
            metadata["alignment_review_match_type"] = match_type
        reviewed_name = (
            f"{entity.name} ({canonical_id})"
            if reviewed_split and canonical_id and entity.name
            else entity.name
        )
        aligned = replace(
            entity,
            canonical_id=canonical_id,
            name=reviewed_name,
            metadata=metadata,
        )
        aligned_entities.append(aligned)
        if not canonical_id:
            unresolved_records.append(_unresolved_record(aligned))
            continue
        alignment_relation = _alignment_relation_for_entity(
            entity,
            canonical_id=canonical_id,
            match_type=match_type,
            profile=profile,
        )
        if alignment_relation is not None:
            alignment_relations.append(alignment_relation)
        if entity.entity_id_suggestion:
            endpoint_map[entity.entity_id_suggestion] = canonical_id
        if entity.canonical_id:
            endpoint_map[entity.canonical_id] = canonical_id
        for alias in entity.aliases:
            endpoint_map[alias] = canonical_id
        identities = (
            _reviewed_split_identities(aligned)
            if reviewed_split
            else _entity_identities(aligned)
        )
        for identity in identities:
            prior = canonical_by_identity.get(identity)
            if prior is not None and prior != canonical_id:
                conflict = {
                    "identity": identity,
                    "left_canonical_id": prior,
                    "right_canonical_id": canonical_id,
                    "entity_id_suggestion": entity.entity_id_suggestion,
                    "draft_id": entity.draft_id,
                    "source_id": entity.source_id,
                    "scenario": entity.scenario,
                    "name": entity.name,
                    "label": entity.label,
                    "evidence": entity.evidence or entity.evidence_span or entity.draft_id,
                    "confidence": entity.confidence,
                }
                conflicts.append(conflict)
                conflict_records.append(
                    _conflict_record(conflict, entity=aligned)
                )
            canonical_by_identity[identity] = canonical_id

    aligned_relations = tuple(
        replace(
            relation,
            head=endpoint_map.get(relation.head, relation.head),
            tail=endpoint_map.get(relation.tail, relation.tail),
        )
        for relation in draft.relations
    )
    return AlignmentResult(
        draft=DraftKG(
            entities=tuple(aligned_entities),
            relations=aligned_relations,
        ),
        alignment_relations=tuple(alignment_relations),
        canonical_entities=_canonical_entity_table(aligned_entities),
        merge_candidates=tuple(candidates),
        unresolved_entities=tuple(
            entity for entity in aligned_entities if not entity.canonical_id
        ),
        unresolved_records=tuple(unresolved_records),
        conflicts=tuple(conflicts),
        conflict_records=tuple(conflict_records),
    )


def _alignment_review_overrides(
    review_decisions: tuple[KGConstructionReviewDecision, ...],
) -> tuple[dict[str, str], set[str]]:
    canonical_overrides: dict[str, str] = {}
    split_overrides: set[str] = set()
    for decision in review_decisions:
        if decision.target_type not in {
            "entity_merge_candidate",
            "unresolved_entity",
            "entity_alignment_conflict",
        }:
            continue
        source_entity_id = _decision_source_entity_id(decision)
        if not source_entity_id:
            continue
        if decision.action == "accept":
            canonical_id = _decision_canonical_id(decision)
            if canonical_id:
                canonical_overrides[source_entity_id] = canonical_id
                split_overrides.discard(source_entity_id)
        elif decision.action == "reject" and decision.target_type == "entity_merge_candidate":
            canonical_overrides.pop(source_entity_id, None)
            split_overrides.add(source_entity_id)
    return canonical_overrides, split_overrides


def _decision_source_entity_id(decision: KGConstructionReviewDecision) -> str:
    for payload in _decision_payloads(decision):
        value = payload.get("source_entity_id") or payload.get("entity_id_suggestion")
        if value:
            return str(value)
    if decision.target_type == "entity_merge_candidate":
        text = decision.target_key.removeprefix("entity_merge_candidate:")
        if "->" in text:
            return text.split("->", maxsplit=1)[0]
    return ""


def _decision_canonical_id(decision: KGConstructionReviewDecision) -> str:
    for payload in _decision_payloads(decision):
        for key in ("reviewed_canonical_id", "selected_canonical_id", "canonical_id"):
            value = payload.get(key)
            if value:
                return str(value)
    if decision.target_type == "entity_merge_candidate" and "->" in decision.target_key:
        return decision.target_key.split("->", maxsplit=1)[1]
    return ""


def _decision_payloads(
    decision: KGConstructionReviewDecision,
) -> tuple[dict[str, Any], ...]:
    payloads: list[dict[str, Any]] = []
    if isinstance(decision.proposed_payload, dict):
        payloads.append(dict(decision.proposed_payload))
    metadata = decision.metadata
    item = metadata.get("item") if isinstance(metadata, dict) else None
    if isinstance(item, dict):
        payloads.append(dict(item))
        candidate = item.get("candidate_payload")
        if isinstance(candidate, dict):
            payloads.append(dict(candidate))
    return tuple(payloads)


def _entity_identities(entity: DraftEntity) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in (entity.canonical_id, entity.entity_id_suggestion):
        if normalized := normalize_text(value):
            identities.add(f"id:{normalized}")
    if normalized_name := normalize_text(entity.name):
        identities.add(f"name:{entity.label}:{normalized_name}")
    for alias in entity.aliases:
        if normalized_alias := normalize_text(alias):
            identities.add(f"alias:{entity.label}:{normalized_alias}")
    external_id = str(entity.metadata.get("external_id") or "")
    if normalized_external_id := normalize_text(external_id):
        identities.add(f"external:{normalized_external_id}")
    return tuple(sorted(identities))


def _reviewed_split_identities(entity: DraftEntity) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in (entity.canonical_id, entity.entity_id_suggestion):
        if normalized := normalize_text(value):
            identities.add(f"id:{normalized}")
    external_id = str(entity.metadata.get("external_id") or "")
    if normalized_external_id := normalize_text(external_id):
        identities.add(f"external:{normalized_external_id}")
    return tuple(sorted(identities))


def _canonical_entity_table(
    entities: list[DraftEntity],
) -> tuple[CanonicalEntityEntry, ...]:
    grouped: dict[str, list[DraftEntity]] = {}
    for entity in entities:
        if entity.canonical_id:
            grouped.setdefault(entity.canonical_id, []).append(entity)
    rows: list[CanonicalEntityEntry] = []
    for canonical_id in sorted(grouped):
        members = grouped[canonical_id]
        primary = members[0]
        rows.append(
            CanonicalEntityEntry(
                canonical_id=canonical_id,
                name=primary.name,
                label=primary.label,
                scenario=primary.scenario,
                source_entity_ids=tuple(
                    sorted(
                        {
                            entity.entity_id_suggestion
                            for entity in members
                            if entity.entity_id_suggestion
                        }
                    )
                ),
                draft_ids=tuple(sorted({entity.draft_id for entity in members})),
                source_ids=tuple(sorted({entity.source_id for entity in members})),
                aliases=tuple(
                    sorted(
                        {
                            alias
                            for entity in members
                            for alias in entity.aliases
                            if alias
                        }
                    )
                ),
                external_ids=tuple(
                    sorted(
                        {
                            str(entity.metadata.get("external_id") or "").strip()
                            for entity in members
                            if str(entity.metadata.get("external_id") or "").strip()
                        }
                    )
                ),
                evidence_refs=tuple(
                    sorted(
                        {
                            entity.evidence or entity.evidence_span or entity.draft_id
                            for entity in members
                            if entity.evidence or entity.evidence_span or entity.draft_id
                        }
                    )
                ),
                confidence=round(
                    min(max(entity.confidence, 0.0) for entity in members),
                    4,
                ),
            )
        )
    return tuple(rows)


def _alignment_relation_for_entity(
    entity: DraftEntity,
    *,
    canonical_id: str,
    match_type: str,
    profile: RcaProfile,
) -> DraftRelation | None:
    source_entity_id = entity.entity_id_suggestion.strip()
    if not source_entity_id or source_entity_id == canonical_id:
        return None
    evidence = entity.evidence or entity.evidence_span or entity.draft_id
    confidence = _alignment_relation_confidence(entity, match_type=match_type)
    return DraftRelation(
        draft_id=f"alignment:{entity.draft_id}:{source_entity_id}->{canonical_id}",
        source_id=entity.source_id,
        extractor_name="entity_alignment",
        extractor_version="v1",
        scenario=entity.scenario,
        head=source_entity_id,
        relation="ALIGNS_TO",
        tail=canonical_id,
        evidence=evidence,
        confidence=confidence,
        status="accepted" if match_type == "reviewed_override" else "draft",
        metadata={
            "relation_family": "ALIGNMENT",
            "propagation_enabled": False,
            "alignment_match_type": match_type,
            "alignment_reason": f"deterministic {match_type} match in {profile.domain_id}",
            "source_entity_id": source_entity_id,
            "canonical_id": canonical_id,
            "source_draft_id": entity.draft_id,
            "source_label": entity.label,
            "source_name": entity.name,
            "edge_weight": edge_weight(confidence),
        },
    )


def _alignment_relation_confidence(entity: DraftEntity, *, match_type: str) -> float:
    if match_type == "reviewed_override":
        return 1.0
    if match_type == "alias":
        return min(0.95, max(0.0, entity.confidence))
    if match_type == "reviewed_split":
        return 0.9
    return min(0.99, max(0.0, entity.confidence))


def _alignment_relation_payload(relation: DraftRelation) -> dict[str, object]:
    return {
        "draft_id": relation.draft_id,
        "source_id": relation.source_id,
        "source": relation.source_id,
        "extractor_name": relation.extractor_name,
        "extractor_version": relation.extractor_version,
        "scenario": relation.scenario,
        "head": relation.head,
        "relation": relation.relation,
        "tail": relation.tail,
        "evidence": relation.evidence or relation.evidence_span,
        "confidence": relation.confidence,
        "weight": edge_weight(relation.confidence),
        "review_status": draft_status_to_review_status(relation.status),
        "metadata": dict(relation.metadata),
    }


def _unresolved_record(entity: DraftEntity) -> AlignmentIssueRecord:
    evidence = entity.evidence or entity.evidence_span or entity.draft_id
    return AlignmentIssueRecord(
        issue_id=f"unresolved_entity:{entity.draft_id}",
        issue_type="unresolved_entity",
        source_entity_id=entity.entity_id_suggestion,
        canonical_id=entity.canonical_id,
        reason="entity has no deterministic canonical ID",
        scenario=entity.scenario,
        source_id=entity.source_id,
        evidence=evidence,
        confidence=entity.confidence,
        payload={
            "draft_id": entity.draft_id,
            "entity_id_suggestion": entity.entity_id_suggestion,
            "name": entity.name,
            "label": entity.label,
            "aliases": list(entity.aliases),
            "external_id": str(entity.metadata.get("external_id") or ""),
        },
    )


def _conflict_record(
    conflict: dict[str, object],
    *,
    entity: DraftEntity,
) -> AlignmentIssueRecord:
    evidence = str(conflict.get("evidence") or entity.evidence or entity.draft_id)
    identity = str(conflict.get("identity") or "")
    return AlignmentIssueRecord(
        issue_id=f"alignment_conflict:{identity}:{entity.draft_id}",
        issue_type="alignment_conflict",
        source_entity_id=entity.entity_id_suggestion,
        canonical_id=entity.canonical_id,
        reason="deterministic alignment found conflicting canonical IDs",
        scenario=entity.scenario,
        source_id=entity.source_id,
        evidence=evidence,
        confidence=entity.confidence,
        payload=dict(conflict),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
