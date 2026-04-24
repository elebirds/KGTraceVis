"""Shared result models for script and app clients."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """Stable output envelope for KGTraceVis analysis."""

    case_id: str
    linked_entities: list[dict] = Field(default_factory=list)
    consistency_score: float | None = None
    inconsistent_fields: list[str] = Field(default_factory=list)
    correction_candidates: list[dict] = Field(default_factory=list)
    top_k_paths: list[dict] = Field(default_factory=list)
    human_feedback: dict | None = None
