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


def _edge(
    head: str,
    tail: str,
    *,
    scenario: str,
    confidence: float,
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
    )
