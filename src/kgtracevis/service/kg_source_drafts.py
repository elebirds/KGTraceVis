"""Source-to-KG candidate draft generation for RootLens KG Studio."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.kg_construction.confidence_assigner import edge_weight

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
    edges = [
        edge
        for line in request.source_text.splitlines()
        if (edge := _edge_from_line(line, request)) is not None
    ]
    return KGSourceDraftResponse(
        provider=request.provider,
        source_id=request.source_id,
        claim_boundary="candidate/plausible explanation only; not a verified root-cause label",
        candidate_edges=edges,
    )


def _edge_from_line(
    line: str,
    request: KGSourceDraftRequest,
) -> KGSourceDraftEdge | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    row = next(csv.reader(StringIO(stripped)))
    if len(row) < 3:
        return None
    head = row[0].strip()
    relation = row[1].strip()
    tail = row[2].strip()
    scenario = row[3].strip() if len(row) >= 4 and row[3].strip() else request.default_scenario
    evidence = row[4].strip() if len(row) >= 5 and row[4].strip() else stripped
    if not head or not relation or not tail or not scenario:
        return None
    edge_id = "|".join([head, relation, tail, scenario])
    return KGSourceDraftEdge(
        edge_id=edge_id,
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        source=request.source_id,
        evidence=evidence,
        confidence=request.confidence,
        weight=edge_weight(request.confidence),
        review_status="auto",
    )

