"""Tests for reusable root-cause reasoner construction."""

from __future__ import annotations

import pytest

from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.workflows.root_cause_provider_selection import (
    ProfileResolvingReasoner,
    build_pipeline,
    build_root_cause_reasoner,
)


def test_root_cause_reasoner_is_profile_resolver() -> None:
    """Pipeline construction should use the profile-resolving RCA reasoner."""
    provider = build_root_cause_reasoner()
    pipeline = build_pipeline()

    assert isinstance(provider, ProfileResolvingReasoner)
    assert isinstance(pipeline.root_cause_reasoner, ProfileResolvingReasoner)


def test_default_profile_resolver_keeps_non_tep_cases_on_generic_paths() -> None:
    """Non-TEP Evidence should continue to use generic graph-path RCA by default."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    result = build_pipeline(graph=KnowledgeGraph.from_default_paths()).analyze(evidence, top_k=2)

    assert result.top_k_paths
    assert result.ranked_root_causes
    assert all(
        root_cause.scoring_method != "tep_root_kgd"
        for root_cause in result.ranked_root_causes
    )
    assert result.reasoning_metadata["reasoning_profile_id"] == "generic_graph_path_default"
    assert result.reasoning_metadata["selection_mode"] == "default"


def test_default_profile_resolver_keeps_tep_cases_on_root_kgd() -> None:
    """TEP Evidence should continue to use the Root-KGD adapter by default."""
    evidence = load_evidence_json("data/examples/tep_example.json")
    result = build_pipeline(graph=KnowledgeGraph.from_default_paths()).analyze(evidence, top_k=2)

    assert result.top_k_paths
    assert result.ranked_root_causes
    assert all(
        root_cause.scoring_method == "tep_root_kgd"
        for root_cause in result.ranked_root_causes
    )
    assert result.reasoning_metadata["reasoning_profile_id"] == "tep_root_kgd_default"
    assert result.reasoning_metadata["reasoner_adapter"] == "tep_root_kgd"
    assert result.reasoning_metadata["selection_mode"] == "default"


def test_explicit_generic_profile_allows_tep_generic_baseline() -> None:
    """TEP should allow an explicit generic graph-path baseline profile."""
    evidence = load_evidence_json("data/examples/tep_example.json")
    result = build_pipeline(
        graph=KnowledgeGraph.from_default_paths(),
        reasoning_profile_id="generic_graph_path_default",
    ).analyze(evidence, top_k=2)

    assert result.top_k_paths
    assert result.ranked_root_causes
    assert all(
        root_cause.scoring_method == "relation_weighted_path"
        for root_cause in result.ranked_root_causes
    )
    assert result.reasoning_metadata["reasoning_profile_id"] == "generic_graph_path_default"
    assert result.reasoning_metadata["reasoner_adapter"] == "generic_graph_path"
    assert result.reasoning_metadata["selection_mode"] == "explicit"


def test_explicit_incompatible_profile_is_rejected() -> None:
    """Explicit profile selection should fail when dataset scope is incompatible."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    pipeline = build_pipeline(
        graph=KnowledgeGraph.from_default_paths(),
        reasoning_profile_id="tep_root_kgd_default",
    )

    with pytest.raises(ValueError, match="not compatible with dataset mvtec"):
        pipeline.analyze(evidence, top_k=2)
