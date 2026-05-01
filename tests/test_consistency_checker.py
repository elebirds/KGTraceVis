"""Tests for KG consistency checking."""

from __future__ import annotations

from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json


def test_clean_mvtec_example_is_consistent() -> None:
    """The checked-in MVTec example should satisfy KG morphology/location rules."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph.from_csv()
    links = link_evidence_entities(evidence, graph)

    result = check_consistency(evidence, graph, links)

    assert result["consistency_score"] == 1.0
    assert result["inconsistent_fields"] == []
