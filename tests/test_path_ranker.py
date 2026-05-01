"""Tests for root-cause path ranking."""

from __future__ import annotations

from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
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
