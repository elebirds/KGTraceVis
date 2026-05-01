"""Shared result models for script and app clients."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisResult(BaseModel):
    """Stable output envelope for KGTraceVis analysis."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    linked_entities: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float | None = None
    inconsistent_fields: list[str] = Field(default_factory=list)
    correction_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_k_paths: list[dict[str, Any]] = Field(default_factory=list)
    human_feedback: dict[str, Any] | None = None
