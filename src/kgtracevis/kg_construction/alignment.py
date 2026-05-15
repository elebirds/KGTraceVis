"""Deterministic entity alignment for DraftKG candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kgtracevis.kg.graph import normalize_text
from kgtracevis.kg_construction.draft import DraftEntity, DraftKG, DraftRelation
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
class AlignmentResult:
    """Output of the entity alignment stage."""

    draft: DraftKG
    alignment_relations: tuple[DraftRelation, ...]
    merge_candidates: tuple[AlignmentCandidate, ...]
    unresolved_entities: tuple[DraftEntity, ...]
    conflicts: tuple[dict[str, object], ...]

    def manifest(self) -> dict[str, object]:
        """Return a JSON-friendly alignment manifest."""
        return {
            "artifact_type": "entity_alignment_manifest_v1",
            "aligned_entity_count": len(self.draft.entities),
            "alignment_relation_count": len(self.alignment_relations),
            "merge_candidate_count": len(self.merge_candidates),
            "unresolved_entity_count": len(self.unresolved_entities),
            "conflict_count": len(self.conflicts),
            "merge_candidates": [candidate.__dict__ for candidate in self.merge_candidates],
            "conflicts": list(self.conflicts),
        }


def run_entity_alignment(draft: DraftKG, profile: RcaProfile) -> AlignmentResult:
    """Apply deterministic ID, alias, external-id, and signal mapping alignment."""
    canonical_by_identity: dict[str, str] = {}
    candidates: list[AlignmentCandidate] = []
    conflicts: list[dict[str, object]] = []
    aligned_entities: list[DraftEntity] = []
    endpoint_map: dict[str, str] = {}
    alignment_relations: list[DraftRelation] = []

    for entity in draft.entities:
        suggested = entity.canonical_id or entity.entity_id_suggestion
        canonical_id = suggested
        match_type = "exact_id"
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
        aligned = replace(entity, canonical_id=canonical_id)
        aligned_entities.append(aligned)
        endpoint_map[entity.entity_id_suggestion] = canonical_id
        endpoint_map[entity.canonical_id] = canonical_id
        for alias in entity.aliases:
            endpoint_map[alias] = canonical_id
        for identity in _entity_identities(aligned):
            prior = canonical_by_identity.get(identity)
            if prior is not None and prior != canonical_id:
                conflicts.append(
                    {
                        "identity": identity,
                        "left": prior,
                        "right": canonical_id,
                        "entity_id_suggestion": entity.entity_id_suggestion,
                    }
                )
            canonical_by_identity[identity] = canonical_id
        external_id = str(entity.metadata.get("external_id") or "").strip()
        if external_id and external_id != canonical_id:
            alignment_relations.append(
                DraftRelation(
                    draft_id=f"{entity.draft_id}:aligns_to",
                    source_id=entity.source_id,
                    extractor_name="entity_alignment",
                    extractor_version="v1",
                    scenario=entity.scenario,
                    head=external_id,
                    relation="ALIGNS_TO",
                    tail=canonical_id,
                    evidence=entity.evidence or entity.draft_id,
                    confidence=0.95,
                    status="auto",
                    metadata={
                        "relation_family": "ALIGNMENT",
                        "propagation_enabled": False,
                    },
                )
            )

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
            relations=(*aligned_relations, *alignment_relations),
        ),
        alignment_relations=tuple(alignment_relations),
        merge_candidates=tuple(candidates),
        unresolved_entities=tuple(
            entity for entity in aligned_entities if not entity.canonical_id
        ),
        conflicts=tuple(conflicts),
    )


def _entity_identities(entity: DraftEntity) -> set[str]:
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
    return identities
