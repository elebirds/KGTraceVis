"""Tests for source-constrained KG construction helpers."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg_construction import (
    CandidateEntity,
    CandidateTriple,
    assign_confidence,
    clean_candidate_nodes,
    clean_candidate_triples,
    export_kg_csv,
    extract_candidate_entities,
    extract_candidate_triples,
    load_source_registry,
    load_source_text,
    validate_edges,
)
from kgtracevis.kg_construction.export_kg_csv import EDGE_COLUMNS, NODE_COLUMNS
from kgtracevis.kg_construction.source_loader import SourceRecord


def test_source_registry_and_text_loading(tmp_path: Path) -> None:
    """Source registry rows should validate and local source text should load."""
    source_file = tmp_path / "sources" / "note.md"
    source_file.parent.mkdir()
    source_file.write_text("structured source note", encoding="utf-8")
    registry_path = tmp_path / "source_registry.csv"
    registry_path.write_text(
        "\n".join(
            [
                "source_id,title,type,path_or_url,used_for,notes",
                f"note_1,Note,project_note,{source_file},testing,local note",
            ]
        ),
        encoding="utf-8",
    )

    records = load_source_registry(registry_path)

    assert records == [
        SourceRecord(
            source_id="note_1",
            title="Note",
            source_type="project_note",
            path_or_url=str(source_file),
            used_for="testing",
            notes="local note",
        )
    ]
    assert load_source_text(records[0]) == "structured source note"


def test_candidate_entity_and_triple_extraction_from_structured_records() -> None:
    """Structured rows should produce explicit candidate nodes and triples."""
    records = [
        {
            "id": "ScratchDefect",
            "name": "Scratch defect",
            "label": "AnomalyType",
            "scenario": "mvtec",
            "aliases": "scratch|scratch defect",
            "description": "Linear visible defect",
            "source": "dataset_labels",
            "head": "ScratchDefect",
            "relation": "HAS_MORPHOLOGY",
            "tail": "LinearMorphology",
            "evidence": "row 1",
            "type": "dataset_label",
        }
    ]

    entities = extract_candidate_entities(records, source_id="dataset_labels")
    triples = extract_candidate_triples(records, source_id="dataset_labels")

    assert entities == [
        CandidateEntity(
            id="ScratchDefect",
            name="Scratch defect",
            label="AnomalyType",
            scenario="mvtec",
            aliases=("scratch", "scratch defect"),
            description="Linear visible defect",
            source="dataset_labels",
            evidence="row 1",
        )
    ]
    assert triples == [
        CandidateTriple(
            head="ScratchDefect",
            relation="HAS_MORPHOLOGY",
            tail="LinearMorphology",
            scenario="mvtec",
            source="dataset_labels",
            evidence="row 1",
            confidence=0.9,
            weight=0.1,
        )
    ]


def test_confidence_assignment_by_source_type() -> None:
    """Source-type confidence assignment should be deterministic and bounded."""
    assert assign_confidence("dataset_label") == 0.9
    assert assign_confidence("llm_extraction") == 0.55
    assert assign_confidence("unknown_source") == 0.6
    assert assign_confidence("dataset_label", explicit_confidence=0.42) == 0.42
    with pytest.raises(ValueError, match="confidence must be in"):
        assign_confidence("dataset_label", explicit_confidence=1.5)


def test_candidate_extraction_requires_source_provenance() -> None:
    """Structured candidates should not be created without a source reference."""
    entity_record = {
        "id": "ScratchDefect",
        "name": "Scratch defect",
        "label": "AnomalyType",
        "scenario": "mvtec",
    }
    triple_record = {
        "head": "ScratchDefect",
        "relation": "HAS_MORPHOLOGY",
        "tail": "LinearMorphology",
        "scenario": "mvtec",
    }

    with pytest.raises(ValueError, match="candidate entity missing required source"):
        extract_candidate_entities([entity_record])
    with pytest.raises(ValueError, match="candidate triple missing required source"):
        extract_candidate_triples([triple_record])


def test_node_and_edge_cleaning_deduplicates_and_protects_reviewed_edges() -> None:
    """Cleaners should deduplicate nodes/edges and reject reviewed overwrites."""
    nodes = clean_candidate_nodes(
        [
            CandidateEntity(
                id="ScratchDefect",
                name="Scratch defect",
                label="AnomalyType",
                scenario="mvtec",
                aliases=("scratch",),
            ),
            CandidateEntity(
                id="ScratchDefect",
                name="Scratch defect",
                label="AnomalyType",
                scenario="mvtec",
                aliases=("scratch defect",),
            ),
        ]
    )
    edges = clean_candidate_triples(
        [
            CandidateTriple(
                head="scratch_defect",
                relation="has morphology",
                tail="linear_morphology",
                scenario="mvtec",
                source="dataset_labels",
                evidence="structured row",
                confidence=0.9,
                weight=0.1,
            ),
            CandidateTriple(
                head="ScratchDefect",
                relation="HAS_MORPHOLOGY",
                tail="LinearMorphology",
                scenario="mvtec",
                source="dataset_labels",
                evidence="structured row",
                confidence=0.9,
                weight=0.1,
            ),
        ]
    )

    assert nodes == [
        KGNode(
            id="ScratchDefect",
            name="Scratch defect",
            label="AnomalyType",
            scenario="mvtec",
            aliases=("scratch", "scratch defect"),
            description="",
        )
    ]
    assert len(edges) == 1
    assert edges[0].relation == "HAS_MORPHOLOGY"
    assert edges[0].weight == 0.1

    reviewed = KGEdge(
        head="ScratchDefect",
        relation="HAS_MORPHOLOGY",
        tail="LinearMorphology",
        scenario="mvtec",
        source="manual_curation",
        evidence="reviewed row",
        confidence=0.82,
        weight=0.18,
        review_status="reviewed",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )
    with pytest.raises(ValueError, match="refusing to overwrite reviewed edge"):
        clean_candidate_triples(edges, existing_edges=[reviewed])


def test_export_kg_csv_uses_required_columns(tmp_path: Path) -> None:
    """Exported CSVs should match node and edge contracts and reload cleanly."""
    nodes_path = tmp_path / "nodes.csv"
    edges_path = tmp_path / "edges.csv"
    nodes = [
        KGNode(
            id="ScratchDefect",
            name="Scratch defect",
            label="AnomalyType",
            scenario="mvtec",
            aliases=("scratch",),
            description="Linear defect",
        ),
        KGNode(
            id="LinearMorphology",
            name="Linear morphology",
            label="Morphology",
            scenario="mvtec",
            aliases=("linear",),
            description="Line shape",
        ),
    ]
    edges = [
        KGEdge(
            head="ScratchDefect",
            relation="HAS_MORPHOLOGY",
            tail="LinearMorphology",
            scenario="mvtec",
            source="dataset_labels",
            evidence="structured row",
            confidence=0.9,
            weight=0.1,
            review_status="auto",
            feedback_count=0,
            accepted_count=0,
            rejected_count=0,
        )
    ]

    export_kg_csv(nodes, edges, nodes_path=nodes_path, edges_path=edges_path)

    with nodes_path.open(newline="", encoding="utf-8") as handle:
        assert csv.DictReader(handle).fieldnames == NODE_COLUMNS
    with edges_path.open(newline="", encoding="utf-8") as handle:
        assert csv.DictReader(handle).fieldnames == EDGE_COLUMNS
    graph = KnowledgeGraph.from_csv(nodes_path, edges_path)
    assert graph.has_edge("ScratchDefect", "HAS_MORPHOLOGY", "LinearMorphology")


def test_edge_contract_validation_requires_provenance_and_default_weight() -> None:
    """Edge validation should reject missing provenance and non-default weight."""
    missing_source = KGEdge(
        head="ScratchDefect",
        relation="HAS_MORPHOLOGY",
        tail="LinearMorphology",
        scenario="mvtec",
        source="",
        evidence="structured row",
        confidence=0.9,
        weight=0.1,
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )
    bad_weight = KGEdge(
        head="ScratchDefect",
        relation="HAS_MORPHOLOGY",
        tail="LinearMorphology",
        scenario="mvtec",
        source="dataset_labels",
        evidence="structured row",
        confidence=0.9,
        weight=0.9,
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )

    with pytest.raises(ValueError, match="edge source is required"):
        validate_edges([missing_source])
    with pytest.raises(ValueError, match="edge weight must equal"):
        validate_edges([bad_weight])


def test_candidate_triples_do_not_extract_from_free_text() -> None:
    """Free text without structured edge fields should not create triples."""
    records = [{"text": "Scratch may be caused by a tool mark."}]

    assert extract_candidate_triples(records) == []
