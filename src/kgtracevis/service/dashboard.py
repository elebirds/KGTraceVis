"""RootLens dashboard bootstrap contract helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.service.runs import RunSummary, list_runs, mvtec_model_presets
from kgtracevis.workflows.reasoning_registry import (
    default_reasoning_registry,
    resolve_default_reasoning_profile_id,
)

DASHBOARD_CLAIM_BOUNDARY = (
    'candidate/plausible explanation only; not a verified root-cause label'
)
DashboardUploadMode = Literal['evidence', 'records', 'image']


class DashboardUploadModeInfo(BaseModel):
    """Frontend-facing upload mode metadata."""

    model_config = ConfigDict(extra='forbid')

    mode: DashboardUploadMode
    label: str
    description: str
    accepted_extensions: list[str]
    required_fields: list[str] = Field(default_factory=list)


class DashboardReasoningProfileOption(BaseModel):
    """One dataset-compatible reasoning profile exposed to dashboard clients."""

    model_config = ConfigDict(extra='forbid')

    profile_id: str
    reasoner_adapter: str
    default: bool = False


class DashboardBootstrap(BaseModel):
    """Initial state envelope for RootLens dashboard clients."""

    model_config = ConfigDict(extra='forbid')

    status: str
    api_version: str
    claim_boundary: str
    supported_datasets: list[str]
    supported_feedback_targets: list[str]
    supported_feedback_actions: list[str]
    upload_modes: list[DashboardUploadModeInfo]
    reasoning_profile_options: dict[str, list[DashboardReasoningProfileOption]]
    mvtec_model_presets: dict[str, Any]
    recent_runs: list[RunSummary]


def dashboard_bootstrap(*, recent_limit: int = 20) -> DashboardBootstrap:
    """Return the stable dashboard bootstrap payload."""
    supported_datasets = ['mvtec', 'tep', 'wafer']
    return DashboardBootstrap(
        status='ok',
        api_version='0.1.0',
        claim_boundary=DASHBOARD_CLAIM_BOUNDARY,
        supported_datasets=supported_datasets,
        supported_feedback_targets=[
            'path',
            'edge',
            'entity_link',
            'correction',
            'root_cause_candidate',
        ],
        supported_feedback_actions=['accept', 'reject', 'needs_review'],
        upload_modes=[
            DashboardUploadModeInfo(
                mode='records',
                label='Producer records',
                description='MVTec, WM811K, or TEP-compatible JSON/JSONL/CSV records.',
                accepted_extensions=['.json', '.jsonl', '.csv'],
            ),
            DashboardUploadModeInfo(
                mode='evidence',
                label='Evidence JSON',
                description='One unified KGTraceVis evidence JSON file.',
                accepted_extensions=['.json'],
            ),
            DashboardUploadModeInfo(
                mode='image',
                label='MVTec image',
                description='One MVTec-style image analyzed through the selected local preset.',
                accepted_extensions=['.png', '.jpg', '.jpeg'],
                required_fields=['dataset', 'object_name', 'model_preset'],
            ),
        ],
        reasoning_profile_options={
            dataset: _reasoning_profile_options(dataset) for dataset in supported_datasets
        },
        mvtec_model_presets={
            'default_preset': 'auto',
            'presets': mvtec_model_presets(),
        },
        recent_runs=list_runs()[:recent_limit],
    )


def _reasoning_profile_options(dataset: str) -> list[DashboardReasoningProfileOption]:
    registry = default_reasoning_registry()
    default_id = resolve_default_reasoning_profile_id(dataset)
    return [
        DashboardReasoningProfileOption(
            profile_id=profile.reasoning_profile_id,
            reasoner_adapter=profile.reasoner_adapter,
            default=profile.reasoning_profile_id == default_id,
        )
        for profile in registry.list_profiles(dataset)
    ]
