"""Source-to-KG candidate draft generation for RootLens KG Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.draft import DraftRelation, draft_relations_from_source_text

SourceDraftProvider = Literal["heuristic"]


class KGSourceDraftRequest(BaseModel):
    """Request to generate source-grounded candidate KG edge drafts."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = "dashboard_source"
    source_text: str
    provider: SourceDraftProvider = "heuristic"
    default_scenario: str = "shared"
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)


class KGSourceDraftEdge(BaseModel):
    """One generated candidate edge draft."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float
    weight: float
    review_status: str
    feedback_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0


class KGSourceDraftResponse(BaseModel):
    """Generated source-to-KG candidate draft response."""

    model_config = ConfigDict(extra="forbid")

    provider: SourceDraftProvider
    source_id: str
    claim_boundary: str
    candidate_edges: list[KGSourceDraftEdge]
    note: str = (
        "Generated source-to-KG rows are candidates for review. They are not "
        "verified facts and are not written to KG CSV files."
    )


def generate_source_kg_draft(request: KGSourceDraftRequest) -> KGSourceDraftResponse:
    """Generate schema-compatible candidate edge drafts from structured source lines."""
    relations = draft_relations_from_source_text(
        source_id=request.source_id,
        source_text=request.source_text,
        extractor_name=request.provider,
        extractor_version="v1",
        default_scenario=request.default_scenario,
        confidence=request.confidence,
    )
    edges = [_edge_from_draft_relation(relation) for relation in relations]
    return KGSourceDraftResponse(
        provider=request.provider,
        source_id=request.source_id,
        claim_boundary="candidate/plausible explanation only; not a verified root-cause label",
        candidate_edges=edges,
    )


def _edge_from_draft_relation(relation: DraftRelation) -> KGSourceDraftEdge:
    edge_id = "|".join([relation.head, relation.relation, relation.tail, relation.scenario])
    return KGSourceDraftEdge(
        edge_id=edge_id,
        head=relation.head,
        relation=relation.relation,
        tail=relation.tail,
        scenario=relation.scenario,
        source=relation.source_id,
        evidence=relation.evidence,
        confidence=relation.confidence,
        weight=edge_weight(relation.confidence),
        review_status="auto",
    )
