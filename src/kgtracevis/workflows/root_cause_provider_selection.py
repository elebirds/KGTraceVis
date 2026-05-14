"""Reusable TEP RCA reasoner selection for KGTracePipeline clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.pipeline import KGSnapshotRepository
from kgtracevis.core.rca import RcaReasoner
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.workflows.tep_rca import TepSimpleRcaProvider
from kgtracevis.workflows.tep_root_kgd import TepRootKgdRcaProvider

RootCauseProviderSelection = Literal["none", "native", "simple"]

ENV_TEP_RCA_PROVIDER = "KGTRACEVIS_TEP_RCA_PROVIDER"


@dataclass(frozen=True)
class RootCauseProviderSelectionConfig:
    """Configuration for optional TEP RCA reasoner construction."""

    tep_rca_provider: RootCauseProviderSelection = "none"


def root_cause_provider_config_from_env(
    *,
    provider: str | None = None,
) -> RootCauseProviderSelectionConfig:
    """Resolve explicit TEP RCA options with environment-variable fallbacks."""
    provider_value = provider if provider is not None else os.getenv(ENV_TEP_RCA_PROVIDER)
    return RootCauseProviderSelectionConfig(
        tep_rca_provider=normalize_root_cause_provider_selection(provider_value),
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
    if normalized in {"simple", "fallback"}:
        return "simple"
    raise ValueError("tep_rca_provider must be one of none, native, simple")


def build_root_cause_reasoner(
    config: RootCauseProviderSelectionConfig | None = None,
) -> RcaReasoner | None:
    """Build the selected optional TEP RCA reasoner."""
    selection = config or RootCauseProviderSelectionConfig()
    if selection.tep_rca_provider == "none":
        return None
    if selection.tep_rca_provider == "native":
        return TepRootKgdRcaProvider()
    if selection.tep_rca_provider == "simple":
        return TepSimpleRcaProvider()
    raise ValueError("tep_rca_provider must be one of none, native, simple")


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
