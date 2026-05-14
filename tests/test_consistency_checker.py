"""Tests for KG consistency checking."""

from __future__ import annotations

from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json


def test_clean_mvtec_example_is_consistent() -> None:
    """The checked-in MVTec example should satisfy KG morphology/location rules."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph.from_csv()
    links = link_evidence_entities(evidence, graph)

    result = check_consistency(evidence, graph, links)

    assert result["consistency_score"] == 1.0
    assert result["inconsistent_fields"] == []


def test_consistency_ignores_relations_outside_evidence_scenario() -> None:
    """Scenario-mismatched support edges should not make evidence consistent."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "DefectType", "mvtec", ("scratch",)),
            KGNode(
                "LinearMorphology",
                "Linear morphology",
                "Morphology",
                "mvtec",
                ("linear",),
            ),
            KGNode(
                "SurfaceLocation",
                "Surface location",
                "Location",
                "mvtec",
                ("surface",),
            ),
        ],
        edges=[
            KGEdge(
                head="ScratchDefect",
                relation="HAS_MORPHOLOGY",
                tail="LinearMorphology",
                scenario="wafer",
                source="test_consistency_checker",
                evidence="Scenario-mismatched test edge",
                confidence=0.99,
                weight=0.01,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            ),
            KGEdge(
                head="ScratchDefect",
                relation="OCCURS_ON",
                tail="SurfaceLocation",
                scenario="mvtec",
                source="test_consistency_checker",
                evidence="Scenario-scoped location support",
                confidence=0.90,
                weight=0.10,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            )
        ],
    )
    links = link_evidence_entities(evidence, graph)

    result = check_consistency(evidence, graph, links)

    assert result["consistency_score"] < 1.0
    assert result["inconsistent_fields"] == ["anomaly_type", "morphology"]
