"""Tests for KGTraceVis-native TEP RCA ranking."""

from __future__ import annotations

from kgtracevis.adapters.tep_adapter import evidence_from_tep_record
from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.workflows.tep_rca import (
    TepNativeRcaProvider,
    extract_tep_variable_evidence,
)


def test_extract_tep_variable_evidence_from_multiple_fields() -> None:
    """Native RCA should find variable evidence beyond raw top-level fields."""
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_native_extract",
            "variables": ["XMEAS_1"],
            "variable_contributions": {"XMEAS_1": 0.4},
            "extra": {
                "graph_contributions": {"variable:xmeas_2": 0.2},
            },
        }
    ).model_copy(
        update={
            "normalized_evidence": {
                "variable_scores": {"XMV_4": 0.9},
            }
        }
    )

    variables = extract_tep_variable_evidence(evidence)

    assert {item.variable: item.contribution for item in variables} == {
        "xmeas1": 0.4,
        "xmeas2": 0.2,
        "xmv4": 0.9,
    }


def test_tep_native_provider_ranks_candidates_from_kg_support() -> None:
    """Contribution-weighted KG support should determine native candidate order."""
    graph = _native_tep_graph()
    provider = TepNativeRcaProvider(graph)
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_native_0001",
            "fault_number": 1,
            "simulation_run": 3,
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.8, "XMEAS_2": 0.2},
        }
    )

    ranked = provider.rank_root_causes(evidence, top_k=5)

    assert [item.candidate_id for item in ranked] == ["CoolingFault", "FeedFault"]
    assert ranked[0].scoring_method == "tep_native_kg"
    assert ranked[0].ranking_id == "rca_tep_native_0001_coolingfault"
    assert ranked[0].evidence_match == 0.8
    assert ranked[0].explanation_paths[0]["nodes"] == ["CoolingFault", "XMEAS_1"]
    assert ranked[0].supporting_edges[0]["edge_id"] == (
        "CoolingFault|AFFECTS_VARIABLE|XMEAS_1|tep"
    )
    assert ranked[0].supporting_evidence[0]["variable"] == "XMEAS_1"
    assert ranked[0].scoring_details["supported_variables"][0]["variable_node_id"] == (
        "XMEAS_1"
    )


def test_tep_native_provider_order_changes_with_variable_contributions() -> None:
    """Changing variable contribution evidence should change native RCA order."""
    graph = _native_tep_graph()
    provider = TepNativeRcaProvider(graph)
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_native_0002",
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.1, "XMEAS_2": 0.9},
        }
    )

    ranked = provider.rank_root_causes(evidence, top_k=5)

    assert [item.candidate_id for item in ranked] == ["FeedFault", "CoolingFault"]


def test_tep_native_provider_requires_tep_dataset_and_kg_support() -> None:
    """Native provider should not emit non-TEP or unsupported KG candidates."""
    graph = _native_tep_graph()
    provider = TepNativeRcaProvider(graph)
    tep_evidence = evidence_from_tep_record(
        {
            "case_id": "tep_native_0003",
            "variables": ["XMEAS_1"],
            "variable_contributions": {"XMEAS_1": 0.8},
        }
    )
    non_tep_evidence = tep_evidence.model_copy(update={"dataset": "wafer"})

    assert provider.rank_root_causes(non_tep_evidence) == []
    ranked = provider.rank_root_causes(tep_evidence, top_k=5)
    assert "UnsupportedFault" not in {item.candidate_id for item in ranked}


def test_pipeline_passes_runtime_graph_to_tep_native_provider() -> None:
    """The unified pipeline should integrate the native provider without route2."""
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_native_pipeline",
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.8, "XMEAS_2": 0.2},
        }
    )
    pipeline = KGTracePipeline(
        graph=_native_tep_graph(),
        root_cause_provider=TepNativeRcaProvider(),
    )

    result = pipeline.analyze(evidence, top_k=2)

    assert result.ranked_root_causes
    assert result.ranked_root_causes[0].candidate_id == "CoolingFault"
    assert result.ranked_root_causes[0].scoring_method == "tep_native_kg"
    assert result.top_k_paths
    assert result.top_k_paths[0]["path_id"] == (
        result.ranked_root_causes[0].explanation_paths[0]["path_id"]
    )
    assert result.top_k_paths[0]["root_cause_candidate_id"] == "CoolingFault"
    assert result.top_k_paths[0]["nodes"] == ["CoolingFault", "XMEAS_1"]


def test_tep_native_provider_uses_default_seed_kg_for_fault_06() -> None:
    """The checked-in TEP seed should support native Fault 06 RCA ranking."""
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_fault_06_seed",
            "anomaly_type": "fault_06",
            "variables": ["XMEAS_1", "XMV_3"],
            "variable_contributions": {"XMEAS_1": 0.7, "XMV_3": 0.3},
        }
    )
    pipeline = KGTracePipeline(
        graph=KnowledgeGraph.from_default_paths(),
        root_cause_provider=TepNativeRcaProvider(),
    )

    result = pipeline.analyze(evidence, top_k=3)

    assert result.ranked_root_causes
    assert result.ranked_root_causes[0].candidate_id == "Fault06Stream1AFeedLoss"
    assert result.ranked_root_causes[0].scoring_method == "tep_native_kg"
    assert {
        path["path_id"]
        for path in result.ranked_root_causes[0].explanation_paths
    }.issubset({path["path_id"] for path in result.top_k_paths})


def _native_tep_graph() -> KnowledgeGraph:
    nodes = [
        KGNode("Process", "Tennessee Eastman process", "Object", "tep", ("process",)),
        KGNode("FaultOne", "Fault one", "FaultType", "tep", ("1",)),
        KGNode("XMEAS_1", "Reactor temperature", "Variable", "tep", ("XMEAS_1",)),
        KGNode("XMEAS_2", "Feed flow", "Variable", "tep", ("XMEAS_2",)),
        KGNode("CoolingFault", "Cooling fault", "FaultType", "tep", ()),
        KGNode("FeedFault", "Feed fault", "FaultType", "tep", ()),
        KGNode("UnsupportedFault", "Unsupported fault", "FaultType", "tep", ()),
    ]
    edges = [
        _edge("CoolingFault", "AFFECTS_VARIABLE", "XMEAS_1", 0.9),
        _edge("FeedFault", "AFFECTS_VARIABLE", "XMEAS_2", 0.9),
        _edge("UnsupportedFault", "AFFECTS_VARIABLE", "XMEAS_1", 0.99, scenario="mvtec"),
    ]
    return KnowledgeGraph(nodes, edges)


def _edge(
    head: str,
    relation: str,
    tail: str,
    confidence: float,
    *,
    scenario: str = "tep",
) -> KGEdge:
    return KGEdge(
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        source="test_tep_native_kg",
        evidence=f"{head} has test KG support for {tail}",
        confidence=confidence,
        weight=round(1.0 - confidence, 4),
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )
