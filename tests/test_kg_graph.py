"""Tests for in-memory KG loading."""

from __future__ import annotations

from kgtracevis.kg.graph import KnowledgeGraph


def test_load_example_kg() -> None:
    """Checked-in KG CSV files should load into the in-memory graph."""
    graph = KnowledgeGraph.from_csv()

    assert "ScratchDefect" in graph.nodes
    assert "NearfullDefect" in graph.nodes
    assert graph.has_edge("ScratchDefect", "HAS_MORPHOLOGY", "LinearMorphology")
