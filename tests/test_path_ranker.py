"""Tests for root-cause path ranking."""

from __future__ import annotations

from kgtracevis.core.rca import GenericGraphPathReasoner
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.validators import load_evidence_json


def test_mvtec_example_returns_root_cause_path() -> None:
    """The MVTec example should return a plausible RCA path."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "Defect", "mvtec", ("scratch",)),
            KGNode("MechanicalContact", "Mechanical contact", "CandidateCause", "mvtec", ()),
        ],
        edges=[
            _edge("ScratchDefect", "MechanicalContact", scenario="mvtec", confidence=0.7),
        ],
    )
    links = link_evidence_entities(evidence, graph)

    paths = rank_root_cause_paths(evidence, graph, links)

    assert paths
    assert paths[0]["source_entity_id"] == "ScratchDefect"
    assert paths[0]["target_entity_id"] in {"MechanicalContact", "HandlingDamage"}


def test_path_ranking_ignores_edges_outside_evidence_scenario() -> None:
    """Mixed graphs should not rank paths through another scenario's edges."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "Defect", "mvtec", ("scratch",)),
            KGNode("MechanicalContact", "Mechanical contact", "CandidateCause", "mvtec", ()),
            KGNode("HandlingDamage", "Handling damage", "CandidateCause", "mvtec", ()),
        ],
        edges=[
            _edge("ScratchDefect", "MechanicalContact", scenario="wafer", confidence=0.99),
            _edge("ScratchDefect", "HandlingDamage", scenario="mvtec", confidence=0.60),
        ],
    )
    links = link_evidence_entities(evidence, graph)

    paths = rank_root_cause_paths(evidence, graph, links)

    assert [path["target_entity_id"] for path in paths] == ["HandlingDamage"]
    assert paths[0]["source_edge_ids"] == [
        "ScratchDefect|HAS_PLAUSIBLE_CAUSE|HandlingDamage|mvtec"
    ]


def test_path_ranking_uses_rca_view_scores_when_available() -> None:
    """Construction RCA score metadata should influence runtime path ranking."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "Defect", "mvtec", ("scratch",)),
            KGNode("LowRcaCause", "Low RCA cause", "CandidateCause", "mvtec", ()),
            KGNode("HighRcaCause", "High RCA cause", "CandidateCause", "mvtec", ()),
        ],
        edges=[
            _edge(
                "ScratchDefect",
                "LowRcaCause",
                scenario="mvtec",
                confidence=0.9,
                rca_score=0.2,
            ),
            _edge(
                "ScratchDefect",
                "HighRcaCause",
                scenario="mvtec",
                confidence=0.7,
                rca_score=0.95,
            ),
        ],
    )
    links = link_evidence_entities(evidence, graph)

    paths = rank_root_cause_paths(evidence, graph, links)

    assert paths[0]["target_entity_id"] == "HighRcaCause"
    assert paths[0]["rca_score"] == 0.95
    assert paths[0]["path_strength"] == 0.95
    assert paths[0]["confidence"] == 0.7
    assert paths[0]["kg_build_ids"] == ["kgbuild_test"]


def test_generic_reasoner_preserves_kg_build_provenance() -> None:
    """RCA outputs should record which construction KG build supported them."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "Defect", "mvtec", ("scratch",)),
            KGNode("HighRcaCause", "High RCA cause", "CandidateCause", "mvtec", ()),
        ],
        edges=[
            _edge(
                "ScratchDefect",
                "HighRcaCause",
                scenario="mvtec",
                confidence=0.7,
                rca_score=0.95,
            ),
        ],
    )
    links = link_evidence_entities(evidence, graph)

    result = GenericGraphPathReasoner().reason_root_causes(
        evidence,
        graph=graph,
        linked_entities=links,
    )

    assert result.metadata["kg_build_ids"] == ["kgbuild_test"]
    assert result.top_k_paths[0]["kg_build_ids"] == ["kgbuild_test"]
    assert result.ranked_root_causes[0].scoring_details["kg_build_ids"] == [
        "kgbuild_test"
    ]


def test_default_csv_path_ranking_targets_root_cause_and_fault_type_labels() -> None:
    """Generic path ranking should discover current CSV RCA target labels."""
    evidence = load_evidence_json("data/examples/tep_example.json")
    graph = KnowledgeGraph.from_default_paths()
    links = link_evidence_entities(evidence, graph)

    paths = rank_root_cause_paths(evidence, graph, links, top_k=10)
    target_labels = {graph.nodes[path["target_entity_id"]].label for path in paths}

    assert "RootCause" in target_labels
    assert "FaultType" in target_labels
    assert any(path["source_entity_id"] == "XMEAS1" for path in paths)


def _edge(
    head: str,
    tail: str,
    *,
    scenario: str,
    confidence: float,
    rca_score: float = 0.0,
) -> KGEdge:
    return KGEdge(
        head=head,
        relation="HAS_PLAUSIBLE_CAUSE",
        tail=tail,
        scenario=scenario,
        source="test_path_ranker",
        evidence=f"{head} test support for {tail}",
        confidence=confidence,
        weight=round(1.0 - confidence, 4),
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
        propagation_enabled=rca_score > 0,
        rca_score=rca_score,
        kg_build_id="kgbuild_test" if rca_score > 0 else "",
    )
