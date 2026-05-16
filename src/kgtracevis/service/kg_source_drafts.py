"""Heuristic source-text preview for KG Studio."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateEdge(BaseModel):
    """Reviewable KG edge candidate preview."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    review_status: str = "auto"
    feedback_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0


class KGSourceDraftRequest(BaseModel):
    """Request to preview source-backed candidate rows."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = "source_draft"
    source_text: str
    provider: str = "heuristic"
    default_scenario: str = "shared"
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)


class KGSourceDraftResponse(BaseModel):
    """Preview response for source-backed candidate rows."""

    model_config = ConfigDict(extra="forbid")

    status: str = "generated"
    provider: str
    source_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    candidate_edges: list[CandidateEdge]
    claim_boundary: str = (
        "source draft output is a preview only and is not written to the KG"
    )


def generate_source_kg_draft(request: KGSourceDraftRequest) -> KGSourceDraftResponse:
    """Generate a simple preview from CSV-like source text."""
    nodes: dict[str, dict[str, Any]] = {}
    candidate_edges: list[CandidateEdge] = []
    for row in _source_rows(request):
        head = row["head"]
        relation = row["relation"].upper()
        tail = row["tail"]
        scenario = row["scenario"]
        evidence = row["evidence"]
        confidence = row["confidence"]
        if not head or not tail:
            continue
        nodes.setdefault(
            head,
            {
                "id": head,
                "name": row.get("name") or head,
                "label": row.get("label") or "Concept",
                "scenario": scenario,
            },
        )
        nodes.setdefault(
            tail,
            {
                "id": tail,
                "name": tail,
                "label": "Concept",
                "scenario": scenario,
            },
        )
        candidate_edges.append(
            CandidateEdge(
                edge_id=f"{head}|{relation}|{tail}|{scenario}",
                head=head,
                relation=relation,
                tail=tail,
                scenario=scenario,
                source=request.source_id,
                evidence=evidence,
                confidence=confidence,
                weight=round(1.0 - confidence, 6),
                review_status="auto",
            )
        )
    edges = [
        {
            "target_key": f"{request.source_id}:{index}",
            **edge.model_dump(mode="json"),
        }
        for index, edge in enumerate(candidate_edges)
    ]
    return KGSourceDraftResponse(
        provider=request.provider,
        source_id=request.source_id,
        nodes=list(nodes.values()),
        edges=edges,
        candidate_edges=candidate_edges,
    )


def _source_rows(request: KGSourceDraftRequest) -> list[dict[str, Any]]:
    """Parse source text as header CSV or compact edge lines."""
    lines = [
        line.strip()
        for line in request.source_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return []
    first_fields = [field.strip().lower() for field in next(csv.reader([lines[0]]))]
    if {"head", "relation", "tail"}.issubset(set(first_fields)):
        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(StringIO("\n".join(lines)))
        for row in reader:
            head = (row.get("head") or row.get("id") or "").strip()
            tail = (row.get("tail") or "").strip()
            relation = (row.get("relation") or "MENTIONS").strip()
            scenario = (row.get("scenario") or request.default_scenario).strip()
            evidence = (row.get("evidence") or ",".join(row.values())).strip()
            rows.append(
                {
                    "head": head,
                    "relation": relation,
                    "tail": tail,
                    "scenario": scenario,
                    "source": request.source_id,
                    "evidence": evidence,
                    "confidence": float(row.get("confidence") or request.confidence),
                    "name": row.get("name"),
                    "label": row.get("label"),
                }
            )
        return rows

    rows = []
    for line in lines:
        fields = [field.strip() for field in next(csv.reader([line]))]
        if len(fields) < 3:
            continue
        scenario = fields[3] if len(fields) >= 4 and fields[3] else request.default_scenario
        evidence = fields[4] if len(fields) >= 5 and fields[4] else line
        rows.append(
            {
                "head": fields[0],
                "relation": fields[1],
                "tail": fields[2],
                "scenario": scenario,
                "source": request.source_id,
                "evidence": evidence,
                "confidence": request.confidence,
                "name": None,
                "label": None,
            }
        )
    return rows
