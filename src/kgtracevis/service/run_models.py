"""Run-session response models shared by service and runtime stores."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

UploadMode = Literal["evidence", "records", "image"]
RunStatus = Literal["completed", "failed"]


class WorkflowStep(BaseModel):
    """One visible step in an uploaded-sample or evidence analysis run."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: str
    status: RunStatus
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Compact metadata for the run list."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: str
    mode: UploadMode
    source_filename: str
    top_k: int
    run_dir: str
    status: RunStatus = "completed"
    dataset: str | None = None
    case_count: int = 0
    evidence_count: int = 0
    label: str
    model_preset: str | None = None
    model_backend: str | None = None


class RunDetail(BaseModel):
    """Persisted detail record for one uploaded sample run."""

    model_config = ConfigDict(extra="forbid")

    run: RunSummary
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    claim_boundary: str
    evidence: dict[str, Any] | None = None
    evidence_summary: dict[str, Any] | None = None
    evidence_with_analysis: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    cases: list[dict[str, Any]] = Field(default_factory=list)
    linked_entities: list[dict[str, Any]] = Field(default_factory=list)
    correction_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_k_paths: list[dict[str, Any]] = Field(default_factory=list)
    ranked_root_causes: list[dict[str, Any]] = Field(default_factory=list)
    path_graph: dict[str, Any] = Field(default_factory=dict)
    source_edge_provenance: list[dict[str, Any]] = Field(default_factory=list)
    review_targets: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    visual_evidence: list[dict[str, Any]] = Field(default_factory=list)
