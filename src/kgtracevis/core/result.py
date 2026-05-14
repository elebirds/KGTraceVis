"""Shared result models for script and app clients."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RankedRootCause(BaseModel):
    """Unified, feedback-compatible root-cause candidate ranking item."""

    model_config = ConfigDict(extra="forbid")

    ranking_id: str
    rank: int = Field(ge=1)
    candidate_id: str
    candidate_name: str
    candidate_label: str | None = None
    candidate_role: str | None = None
    score: float
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_match: float | None = Field(default=None, ge=0.0, le=1.0)
    explanation_paths: list[dict[str, Any]] = Field(default_factory=list)
    supporting_edges: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    scoring_method: str
    scoring_details: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    review_status: str = "auto"


class RcaRankingResult(BaseModel):
    """Unified RCA ranking result produced by a path or scenario-specific strategy."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    ranked_root_causes: list[RankedRootCause] = Field(default_factory=list)
    scoring_method: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    """Stable output envelope for KGTraceVis analysis."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    linked_entities: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float | None = None
    inconsistent_fields: list[str] = Field(default_factory=list)
    correction_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_k_paths: list[dict[str, Any]] = Field(default_factory=list)
    ranked_root_causes: list[RankedRootCause] = Field(default_factory=list)
    human_feedback: dict[str, Any] | None = None


def ranked_root_causes_from_paths(
    case_id: str,
    top_k_paths: list[dict[str, Any]],
) -> list[RankedRootCause]:
    """Project ranked path output into the unified root-cause ranking contract."""
    candidates: dict[str, dict[str, Any]] = {}
    for path in top_k_paths:
        candidate_id = str(path.get("target_entity_id") or "")
        if not candidate_id:
            continue
        candidate = candidates.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "candidate_name": _path_candidate_name(path, candidate_id),
                "candidate_label": "RootCause",
                "candidate_role": "path_target",
                "score": float(path.get("score") or 0.0),
                "confidence": _optional_float(path.get("confidence")),
                "evidence_match": _optional_float(path.get("evidence_match")),
                "explanation_paths": [],
                "supporting_edges_by_id": {},
                "supporting_evidence": [],
                "source_path_ids": [],
            },
        )
        score = float(path.get("score") or 0.0)
        if score > float(candidate["score"]):
            candidate["score"] = score
            candidate["confidence"] = _optional_float(path.get("confidence"))
            candidate["evidence_match"] = _optional_float(path.get("evidence_match"))
            candidate["candidate_name"] = _path_candidate_name(path, candidate_id)
        candidate["explanation_paths"].append(dict(path))
        if path.get("path_id"):
            candidate["source_path_ids"].append(str(path["path_id"]))
        for edge in _dict_items(path.get("source_edges")):
            edge_id = str(edge.get("edge_id") or "")
            if edge_id:
                candidate["supporting_edges_by_id"].setdefault(edge_id, edge)
        for index, evidence in enumerate(path.get("supporting_evidence") or []):
            candidate["supporting_evidence"].append(
                {
                    "evidence_id": f"{path.get('path_id', candidate_id)}_evidence_{index + 1}",
                    "source": "kg_path_edge",
                    "text": str(evidence),
                }
            )

    ranked_rows = sorted(
        candidates.values(),
        key=lambda item: (-float(item["score"]), str(item["candidate_id"])),
    )
    return [
        RankedRootCause(
            ranking_id=_ranking_id(case_id, str(item["candidate_id"])),
            rank=index,
            candidate_id=str(item["candidate_id"]),
            candidate_name=str(item["candidate_name"]),
            candidate_label=item.get("candidate_label"),
            candidate_role=item.get("candidate_role"),
            score=round(float(item["score"]), 4),
            confidence=item.get("confidence"),
            evidence_match=item.get("evidence_match"),
            explanation_paths=list(item["explanation_paths"]),
            supporting_edges=[
                item["supporting_edges_by_id"][edge_id]
                for edge_id in sorted(item["supporting_edges_by_id"])
            ],
            supporting_evidence=list(item["supporting_evidence"]),
            scoring_method="relation_weighted_path",
            scoring_details={"source_path_ids": list(item["source_path_ids"])},
            source="top_k_paths_projection",
            review_status="auto",
        )
        for index, item in enumerate(ranked_rows, start=1)
    ]


def _ranking_id(case_id: str, candidate_id: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", candidate_id).strip("_").lower()
    return f"rca_{case_id}_{token or 'candidate'}"


def _path_candidate_name(path: dict[str, Any], candidate_id: str) -> str:
    nodes = path.get("nodes") or []
    names = path.get("node_names") or []
    if nodes and names and nodes[-1] == candidate_id and len(names) >= len(nodes):
        return str(names[-1])
    return candidate_id


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
