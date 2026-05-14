"""Tests for reusable root-cause provider selection."""

from __future__ import annotations

import pytest

from kgtracevis.workflows.root_cause_provider_selection import (
    ENV_TEP_RCA_PROVIDER,
    RootCauseProviderSelectionConfig,
    build_pipeline,
    build_root_cause_reasoner,
    normalize_root_cause_provider_selection,
    root_cause_provider_config_from_env,
)
from kgtracevis.workflows.tep_rca import TepSimpleRcaProvider
from kgtracevis.workflows.tep_root_kgd import TepRootKgdRcaProvider


def test_root_cause_provider_selection_defaults_to_no_provider() -> None:
    """Default selection should preserve existing path-projection behavior."""
    assert normalize_root_cause_provider_selection(None) == "none"
    assert normalize_root_cause_provider_selection("default") == "none"
    assert build_root_cause_reasoner() is None
    assert build_pipeline().root_cause_reasoner is None


def test_root_cause_provider_selection_builds_native_provider() -> None:
    """Native selection should build the Root-KGD TEP provider."""
    provider = build_root_cause_reasoner(
        RootCauseProviderSelectionConfig(tep_rca_provider="native")
    )

    assert isinstance(provider, TepRootKgdRcaProvider)


def test_root_cause_provider_selection_builds_simple_fallback_provider() -> None:
    """Simple selection should keep the old direct-support KG fallback explicit."""
    provider = build_root_cause_reasoner(
        RootCauseProviderSelectionConfig(tep_rca_provider="simple")
    )

    assert isinstance(provider, TepSimpleRcaProvider)


def test_root_cause_provider_selection_rejects_artifact_mode() -> None:
    """Pipeline selection should not expose precomputed TEP ranking artifacts."""
    with pytest.raises(ValueError, match="none, native, simple"):
        normalize_root_cause_provider_selection("artifact")


def test_root_cause_provider_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Service and scripts can share the same environment-backed config helper."""
    monkeypatch.setenv(ENV_TEP_RCA_PROVIDER, "native")

    config = root_cause_provider_config_from_env()

    assert config.tep_rca_provider == "native"
