"""Tests for entity linking."""

from __future__ import annotations

from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json


def test_link_mvtec_example_entities() -> None:
    """The MVTec example should link its core visual fields."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph.from_csv()

    links = link_evidence_entities(evidence, graph)
    selected = {link["field"]: link["selected_entity_id"] for link in links}

    assert selected["anomaly_type"] == "ScratchDefect"
    assert selected["morphology"] == "LinearMorphology"
    assert selected["location"] == "SurfaceLocation"
