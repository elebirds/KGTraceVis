"""Reusable TEP RCA reasoner selection for KGTracePipeline clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.pipeline import KGSnapshotRepository
from kgtracevis.core.rca import RcaReasoner
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.workflows.tep_rca import (
    TepNativeRcaProvider,
    TepRcaArtifactConfig,
    TepRcaArtifactProvider,
)

RootCauseProviderSelection = Literal["none", "native", "artifact"]

ENV_TEP_RCA_PROVIDER = "KGTRACEVIS_TEP_RCA_PROVIDER"
ENV_TEP_RCA_ARTIFACT_DIR = "KGTRACEVIS_TEP_RCA_ARTIFACT_DIR"
ENV_TEP_RCA_RANKING_PATH = "KGTRACEVIS_TEP_RCA_RANKING_PATH"
ENV_TEP_RCA_CONTRIBUTIONS_PATH = "KGTRACEVIS_TEP_RCA_CONTRIBUTIONS_PATH"


@dataclass(frozen=True)
class RootCauseProviderSelectionConfig:
    """Configuration for optional TEP RCA reasoner construction."""

    tep_rca_provider: RootCauseProviderSelection = "none"
    tep_rca_artifact_dir: Path | None = None
    tep_rca_ranking_path: Path | None = None
    tep_rca_contributions_path: Path | None = None
    tep_rca_allow_global_rankings: bool = False


def root_cause_provider_config_from_env(
    *,
    provider: str | None = None,
    artifact_dir: str | Path | None = None,
    ranking_path: str | Path | None = None,
    contributions_path: str | Path | None = None,
    allow_global_rankings: bool = False,
) -> RootCauseProviderSelectionConfig:
    """Resolve explicit TEP RCA options with environment-variable fallbacks."""
    provider_value = provider if provider is not None else os.getenv(ENV_TEP_RCA_PROVIDER)
    artifact_value = (
        artifact_dir if artifact_dir is not None else os.getenv(ENV_TEP_RCA_ARTIFACT_DIR)
    )
    ranking_value = (
        ranking_path if ranking_path is not None else os.getenv(ENV_TEP_RCA_RANKING_PATH)
    )
    contributions_value = (
        contributions_path
        if contributions_path is not None
        else os.getenv(ENV_TEP_RCA_CONTRIBUTIONS_PATH)
    )
    return RootCauseProviderSelectionConfig(
        tep_rca_provider=normalize_root_cause_provider_selection(provider_value),
        tep_rca_artifact_dir=_optional_path(artifact_value),
        tep_rca_ranking_path=_optional_path(ranking_value),
        tep_rca_contributions_path=_optional_path(contributions_value),
        tep_rca_allow_global_rankings=allow_global_rankings,
    )


def normalize_root_cause_provider_selection(
    value: str | None,
) -> RootCauseProviderSelection:
    """Normalize CLI/API text into a supported provider selection."""
    normalized = (value or "none").strip().lower()
    if normalized in {"", "default", "none"}:
        return "none"
    if normalized == "native":
        return "native"
    if normalized == "artifact":
        return "artifact"
    raise ValueError("tep_rca_provider must be one of none, native, artifact")


def build_root_cause_reasoner(
    config: RootCauseProviderSelectionConfig | None = None,
) -> RcaReasoner | None:
    """Build the selected optional TEP RCA reasoner."""
    selection = config or RootCauseProviderSelectionConfig()
    if selection.tep_rca_provider == "none":
        return None
    if selection.tep_rca_provider == "native":
        return TepNativeRcaProvider()
    if selection.tep_rca_provider == "artifact":
        if (
            selection.tep_rca_artifact_dir is None
            and selection.tep_rca_ranking_path is None
        ):
            raise ValueError(
                "tep_rca_artifact_dir or tep_rca_ranking_path is required "
                "when tep_rca_provider=artifact"
            )
        provider = TepRcaArtifactProvider(
            TepRcaArtifactConfig(
                artifact_dir=selection.tep_rca_artifact_dir,
                ranking_path=selection.tep_rca_ranking_path,
                contributions_path=selection.tep_rca_contributions_path,
                allow_global_rankings=selection.tep_rca_allow_global_rankings,
            )
        )
        if provider.ranking_path is None:
            raise FileNotFoundError(
                "TEP RCA ranking artifact was not found; pass tep_rca_ranking_path "
                "or a tep_rca_artifact_dir containing a supported ranking file"
            )
        return provider
    raise ValueError("tep_rca_provider must be one of none, native, artifact")


def build_pipeline(
    *,
    graph: KnowledgeGraph | None = None,
    neo4j_repository: KGSnapshotRepository | None = None,
    root_cause_provider_config: RootCauseProviderSelectionConfig | None = None,
) -> KGTracePipeline:
    """Build a KGTracePipeline with optional TEP RCA reasoner selection."""
    return KGTracePipeline(
        graph=graph,
        neo4j_repository=neo4j_repository,
        root_cause_reasoner=build_root_cause_reasoner(root_cause_provider_config),
    )


def _optional_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if str(path) else None
