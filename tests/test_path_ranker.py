"""Tests for root-cause path ranking."""

from __future__ import annotations

from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.validators import load_evidence_json


def test_mvtec_example_returns_root_cause_path() -> None:
    """The MVTec example should return a plausible RCA path."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph.from_default_paths()
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
            KGNode("ScratchDefect", "Scratch defect", "DefectType", "mvtec", ("scratch",)),
            KGNode("MechanicalContact", "Mechanical contact", "RootCause", "mvtec", ()),
            KGNode("HandlingDamage", "Handling damage", "RootCause", "mvtec", ()),
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
            KGNode("ScratchDefect", "Scratch defect", "DefectType", "mvtec", ("scratch",)),
            KGNode("LowRcaCause", "Low RCA cause", "RootCause", "mvtec", ()),
            KGNode("HighRcaCause", "High RCA cause", "RootCause", "mvtec", ()),
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
    )
