"""RootLens dashboard bootstrap contract helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.service.runs import RunSummary, list_runs, mvtec_model_presets

DASHBOARD_CLAIM_BOUNDARY = (
    "candidate/plausible explanation only; not a verified root-cause label"
)
DashboardUploadMode = Literal["evidence", "records", "image"]


class DashboardUploadModeInfo(BaseModel):
    """Frontend-facing upload mode metadata."""

    model_config = ConfigDict(extra="forbid")

    mode: DashboardUploadMode
    label: str
    description: str
    accepted_extensions: list[str]
    required_fields: list[str] = Field(default_factory=list)


class DashboardBootstrap(BaseModel):
    """Initial state envelope for RootLens dashboard clients."""

    model_config = ConfigDict(extra="forbid")

    status: str
    api_version: str
    claim_boundary: str
    supported_datasets: list[str]
    supported_feedback_targets: list[str]
    supported_feedback_actions: list[str]
    upload_modes: list[DashboardUploadModeInfo]
    mvtec_model_presets: dict[str, Any]
    recent_runs: list[RunSummary]


def dashboard_bootstrap(*, recent_limit: int = 20) -> DashboardBootstrap:
    """Return the stable dashboard bootstrap payload."""
    return DashboardBootstrap(
        status="ok",
        api_version="0.1.0",
        claim_boundary=DASHBOARD_CLAIM_BOUNDARY,
        supported_datasets=["mvtec", "tep", "wafer"],
        supported_feedback_targets=["path", "edge", "entity_link", "correction"],
        supported_feedback_actions=["accept", "reject", "needs_review"],
        upload_modes=[
            DashboardUploadModeInfo(
                mode="records",
                label="Producer records",
                description="MVTec, WM811K, or TEP-compatible JSON/JSONL/CSV records.",
                accepted_extensions=[".json", ".jsonl", ".csv"],
            ),
            DashboardUploadModeInfo(
                mode="evidence",
                label="Evidence JSON",
                description="One unified KGTraceVis evidence JSON file.",
                accepted_extensions=[".json"],
            ),
            DashboardUploadModeInfo(
                mode="image",
                label="MVTec image",
                description="One MVTec-style image analyzed through the selected local preset.",
                accepted_extensions=[".png", ".jpg", ".jpeg"],
                required_fields=["dataset", "object_name", "model_preset"],
            ),
        ],
        mvtec_model_presets={
            "default_preset": "auto",
            "presets": mvtec_model_presets(),
        },
        recent_runs=list_runs()[:recent_limit],
    )
