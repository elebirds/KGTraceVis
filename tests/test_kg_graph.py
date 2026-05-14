"""Tests for in-memory KG loading."""

from __future__ import annotations

from kgtracevis.kg.graph import KnowledgeGraph


def test_load_example_kg_single_csv() -> None:
    """Checked-in KG CSV files should load into the in-memory graph."""
    graph = KnowledgeGraph.from_csv()

    assert "ScratchDefect" in graph.nodes
    assert "NearfullDefect" in graph.nodes
    assert graph.has_edge("ScratchDefect", "HAS_MORPHOLOGY", "LinearMorphology")
    assert not graph.has_edge("ScratchDefect", "HAS_PLAUSIBLE_CAUSE", "MechanicalContact")


def test_default_kg_loads_reference_layers() -> None:
    """Default loading should include development reference-layer edges."""
    graph = KnowledgeGraph.from_default_paths()

    assert graph.has_edge("ScratchDefect", "HAS_PLAUSIBLE_CAUSE", "MechanicalContact")
    assert graph.has_edge("MechanicalContact", "PART_OF", "HandlingDamage")


def test_default_kg_loads_tep_seed_layer() -> None:
    """Default loading should include the curated TEP seed KG."""
    graph = KnowledgeGraph.from_default_paths()

    assert "Fault06Stream1AFeedLoss" in graph.nodes
    assert "Xmeas1Variable" in graph.nodes
    assert graph.has_edge(
        "Fault06Stream1AFeedLoss",
        "AFFECTS_VARIABLE",
        "Xmeas1Variable",
        scenario="tep",
    )
    assert graph.has_edge(
        "Xmeas1Variable",
        "INDICATES",
        "Fault06Stream1AFeedLoss",
        scenario="tep",
    )


def test_merge_deduplicates_identical_edges() -> None:
    """Merging the same CSV twice should not duplicate identical edges."""
    graph = KnowledgeGraph.from_paths(
        ["data/kg/nodes.csv"],
        ["data/kg/edges.csv", "data/kg/edges.csv"],
    )
    edge_ids = [edge.edge_id for edge in graph.edges]

    assert len(edge_ids) == len(set(edge_ids))
