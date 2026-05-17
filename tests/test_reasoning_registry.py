"""Tests for built-in reasoning profile manifests and adapter registry."""

from __future__ import annotations

import pytest

from kgtracevis.core.rca import GenericGraphPathReasoner
from kgtracevis.core.reasoning_profile import ReasoningProfileManifest
from kgtracevis.workflows.reasoning_registry import (
    DEFAULT_GENERIC_REASONING_PROFILE_ID,
    DEFAULT_REASONING_PROFILE_DIR,
    DEFAULT_TEP_REASONING_PROFILE_ID,
    default_reasoning_registry,
    resolve_default_reasoning_profile_id,
)
from kgtracevis.workflows.tep_root_kgd import TepRootKgdRcaProvider


def test_builtin_reasoning_profiles_load_with_resolved_assets() -> None:
    """Built-in reasoning profile manifests should load into resolved path objects."""
    registry = default_reasoning_registry()

    generic = registry.resolve_profile(DEFAULT_GENERIC_REASONING_PROFILE_ID)
    tep = registry.resolve_profile(DEFAULT_TEP_REASONING_PROFILE_ID)

    assert isinstance(generic.manifest, ReasoningProfileManifest)
    assert generic.root_dir == (
        DEFAULT_REASONING_PROFILE_DIR / DEFAULT_GENERIC_REASONING_PROFILE_ID
    ).resolve()
    assert generic.reasoner_adapter == "generic_graph_path"
    assert "tep" in generic.dataset_scope
    assert generic.runtime_overlay == {}
    assert generic.reasoning_assets == {}

    assert isinstance(tep.manifest, ReasoningProfileManifest)
    assert tep.root_dir == (
        DEFAULT_REASONING_PROFILE_DIR / DEFAULT_TEP_REASONING_PROFILE_ID
    ).resolve()
    assert tep.reasoner_adapter == "tep_root_kgd"
    assert tep.runtime_overlay["nodes"].is_file()
    assert tep.runtime_overlay["edges"].is_file()
    assert tep.reasoning_assets["variable_mapping"].is_file()
    assert tep.reasoning_assets["anchor_discriminators"].is_file()
    assert tep.reasoning_assets["relation_family_params"].is_file()
    assert tep.reasoning_assets["rca_edge_weights"].is_file()
    assert tep.reasoning_assets["anchor_memory_profiles"].is_file()


def test_reasoning_registry_lists_dataset_compatible_profiles() -> None:
    """Registry listing should surface compatible built-in profiles per dataset."""
    registry = default_reasoning_registry()

    mvtec_ids = [profile.reasoning_profile_id for profile in registry.list_profiles("mvtec")]
    tep_ids = [profile.reasoning_profile_id for profile in registry.list_profiles("tep")]
    wafer_ids = [profile.reasoning_profile_id for profile in registry.list_profiles("wafer")]

    assert mvtec_ids == [DEFAULT_GENERIC_REASONING_PROFILE_ID]
    assert wafer_ids == [DEFAULT_GENERIC_REASONING_PROFILE_ID]
    assert tep_ids == [DEFAULT_GENERIC_REASONING_PROFILE_ID, DEFAULT_TEP_REASONING_PROFILE_ID]


def test_reasoning_registry_builds_registered_reasoners() -> None:
    """Built-in profiles should instantiate their registered RCA adapters."""
    registry = default_reasoning_registry()

    assert isinstance(
        registry.build_reasoner(DEFAULT_GENERIC_REASONING_PROFILE_ID),
        GenericGraphPathReasoner,
    )
    assert isinstance(
        registry.build_reasoner(DEFAULT_TEP_REASONING_PROFILE_ID),
        TepRootKgdRcaProvider,
    )


def test_reasoning_registry_validates_profile_dataset_compatibility() -> None:
    """Explicit profile selection should reject incompatible dataset combinations."""
    registry = default_reasoning_registry()

    generic = registry.validate_profile_for_dataset(
        DEFAULT_GENERIC_REASONING_PROFILE_ID,
        "tep",
    )
    assert generic.reasoning_profile_id == DEFAULT_GENERIC_REASONING_PROFILE_ID

    with pytest.raises(ValueError, match="not compatible with dataset mvtec"):
        registry.validate_profile_for_dataset(DEFAULT_TEP_REASONING_PROFILE_ID, "mvtec")


def test_default_profile_selection_uses_tep_only_for_tep_dataset() -> None:
    """The built-in default profile selector should keep non-TEP on generic RCA."""
    assert resolve_default_reasoning_profile_id("tep") == DEFAULT_TEP_REASONING_PROFILE_ID
    assert resolve_default_reasoning_profile_id("mvtec") == DEFAULT_GENERIC_REASONING_PROFILE_ID
    assert resolve_default_reasoning_profile_id("wafer") == DEFAULT_GENERIC_REASONING_PROFILE_ID
    assert resolve_default_reasoning_profile_id("unknown") == DEFAULT_GENERIC_REASONING_PROFILE_ID
    assert resolve_default_reasoning_profile_id(None) == DEFAULT_GENERIC_REASONING_PROFILE_ID
