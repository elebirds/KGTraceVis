"""Tests for reusable root-cause provider selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from kgtracevis.workflows.root_cause_provider_selection import (
    ENV_TEP_RCA_PROVIDER,
    RootCauseProviderSelectionConfig,
    build_pipeline,
    build_root_cause_reasoner,
    normalize_root_cause_provider_selection,
    root_cause_provider_config_from_env,
)
from kgtracevis.workflows.tep_rca import TepNativeRcaProvider, TepRcaArtifactProvider


def test_root_cause_provider_selection_defaults_to_no_provider() -> None:
    """Default selection should preserve existing path-projection behavior."""
    assert normalize_root_cause_provider_selection(None) == "none"
    assert normalize_root_cause_provider_selection("default") == "none"
    assert build_root_cause_reasoner() is None
    assert build_pipeline().root_cause_reasoner is None


def test_root_cause_provider_selection_builds_native_provider() -> None:
    """Native selection should build the KGTraceVis-native TEP provider."""
    provider = build_root_cause_reasoner(
        RootCauseProviderSelectionConfig(tep_rca_provider="native")
    )

    assert isinstance(provider, TepNativeRcaProvider)


def test_root_cause_provider_selection_builds_artifact_provider() -> None:
    """Artifact selection should build the bridge provider from explicit paths."""
    provider = build_root_cause_reasoner(
        RootCauseProviderSelectionConfig(
            tep_rca_provider="artifact",
            tep_rca_artifact_dir=Path("tests/fixtures/tep_rca"),
        )
    )

    assert isinstance(provider, TepRcaArtifactProvider)


def test_root_cause_provider_selection_requires_artifact_path() -> None:
    """Artifact mode should fail fast without an artifact directory or ranking path."""
    with pytest.raises(ValueError, match="tep_rca_artifact_dir"):
        build_root_cause_reasoner(
            RootCauseProviderSelectionConfig(tep_rca_provider="artifact")
        )


def test_root_cause_provider_selection_requires_artifact_ranking(
    tmp_path: Path,
) -> None:
    """Artifact mode should fail fast when no ranking artifact can be resolved."""
    with pytest.raises(FileNotFoundError, match="TEP RCA ranking artifact"):
        build_root_cause_reasoner(
            RootCauseProviderSelectionConfig(
                tep_rca_provider="artifact",
                tep_rca_artifact_dir=tmp_path,
            )
        )


def test_root_cause_provider_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Service and scripts can share the same environment-backed config helper."""
    monkeypatch.setenv(ENV_TEP_RCA_PROVIDER, "native")

    config = root_cause_provider_config_from_env()

    assert config.tep_rca_provider == "native"
