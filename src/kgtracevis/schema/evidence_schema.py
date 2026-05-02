"""Unified anomaly evidence schema."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DatasetName = Literal["mvtec", "tep", "wafer"]
EvidenceSource = Literal["image", "time_series", "log", "multimodal", "unknown"]


class RawEvidence(BaseModel):
    """Dataset-specific raw information attached to the unified schema."""

    image_region: str | None = None
    heatmap_path: str | None = None
    variables: list[str] = Field(default_factory=list)
    variable_contributions: dict[str, float] = Field(default_factory=dict)
    log_events: list[str] = Field(default_factory=list)
    description: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class EvidenceObservation(BaseModel):
    """One stable observed evidence item produced by an adapter."""

    obs_id: str
    facet: str
    name: str
    display_name: str | None = None
    value: Any | None = None
    value_type: str | None = None
    unit: str | None = None
    direction: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_ref: str | None = None
    raw_ref: str | None = None
    time_window: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdapterMetadata(BaseModel):
    """Metadata describing the adapter boundary for an evidence object."""

    name: str
    version: str | None = None
    produces_root_cause: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGAnalysis(BaseModel):
    """KG analysis fields written by KGTraceVis modules."""

    linked_entities: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float | None = None
    inconsistent_fields: list[str] = Field(default_factory=list)
    correction_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_k_paths: list[dict[str, Any]] = Field(default_factory=list)


class Evidence(BaseModel):
    """Unified anomaly evidence object consumed by the pipeline."""

    case_id: str
    dataset: DatasetName
    source: EvidenceSource = "unknown"
    object: str
    anomaly_type: str
    location: str | None = None
    morphology: str | None = None
    severity: float | None = None
    confidence: float | None = None
    timestamp: str | None = None
    raw_evidence: RawEvidence = Field(default_factory=RawEvidence)
    observations: list[EvidenceObservation] = Field(default_factory=list)
    adapter: AdapterMetadata | None = None
    normalized_evidence: dict[str, Any] = Field(default_factory=dict)
    kg_analysis: KGAnalysis = Field(default_factory=KGAnalysis)
    human_feedback: dict[str, Any] | None = None
