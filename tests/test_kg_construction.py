"""Tests for source-constrained KG construction helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg_construction import (
    CandidateEntity,
    CandidateTriple,
    assign_confidence,
    audit_mvtec_cases,
    build_candidate_kg,
    clean_candidate_nodes,
    clean_candidate_triples,
    export_kg_csv,
    extract_candidate_entities,
    extract_candidate_triples,
    load_source_registry,
    load_source_text,
    validate_candidate_claim_boundaries,
    validate_edges,
    write_candidate_kg_artifacts,
)
from kgtracevis.kg_construction.case_kg_hardening import WAFER_PATTERNS
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


def test_mvtec_case_audit_scores_clean_semantic_case(tmp_path: Path) -> None:
    """Case audit should rank clean, semantic MVTec defects above weak rows."""
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "\n".join(
            [
                (
                    '{"case_id":"mvtec_metal_nut_test_scratch_000","dataset":"mvtec",'
                    '"object":"metal_nut","source_label":"scratch","pred_label":"anomalous",'
                    '"score":9.1,"confidence":0.97,'
                    '"mask_stats":{"area_ratio":0.02}}'
                ),
                (
                    '{"case_id":"mvtec_bottle_test_good_000","dataset":"mvtec",'
                    '"object":"bottle","source_label":"good","pred_label":"normal",'
                    '"score":1.0,"confidence":0.92,'
                    '"mask_stats":{"area_ratio":0.0}}'
                ),
            ]
        ),
        encoding="utf-8",
    )
    table_path = tmp_path / "table.csv"
    table_path.write_text(
        "\n".join(
            [
                (
                    "case_id,dataset,adapter_name,anomaly_type,location,morphology,"
                    "consistency_score,linked_entity_count,correction_candidate_count,"
                    "path_count,top_target_entity_id,top_target_name,top_target_label,"
                    "best_score,explanation_scope,claim_boundary"
                ),
                (
                    "mvtec_metal_nut_test_scratch_000,mvtec,mvtec,scratch,surface,"
                    "linear,1.0,4,0,2,MechanicalContact,Mechanical contact,RootCause,"
                    "0.7,candidate,"
                ),
                (
                    "mvtec_bottle_test_good_000,mvtec,mvtec,good,surface,spot,1.0,2,"
                    "0,0,,,,,candidate,"
                ),
            ]
        ),
        encoding="utf-8",
    )

    rows = audit_mvtec_cases(records_path, table_path)

    assert rows[0].case_id == "mvtec_metal_nut_test_scratch_000"
    assert rows[0].kg_path_specific is True
    assert rows[0].evidence_clean is True
    assert rows[0].explainability_score > rows[1].explainability_score


def test_coverage_first_candidate_kg_covers_wm811k_patterns_and_claims() -> None:
    """Candidate KG should cover all public WM811K pattern classes safely."""
    nodes, edges, summary = build_candidate_kg()
    node_ids = {node.id for node in nodes}
    edge_ids = {edge.edge_id for edge in edges}
    graph_edge_ids = {edge.edge_id for edge in KnowledgeGraph.from_default_paths().edges}

    for spec in WAFER_PATTERNS:
        if spec.node_id != "NearfullDefect":
            assert spec.node_id in node_ids
        assert (
            f"WaferObject|HAS_ANOMALY|{spec.node_id}|wafer" in edge_ids | graph_edge_ids
        )

    assert "LocDefect|HAS_PLAUSIBLE_CAUSE|GlueRemovalInsufficient|wafer" not in edge_ids
    assert validate_candidate_claim_boundaries(edges) == []
    assert summary["wm811k_pattern_coverage"] == [spec.pattern for spec in WAFER_PATTERNS]


def test_candidate_kg_overlay_loads_and_keeps_loc_separate(tmp_path: Path) -> None:
    """Overlay KG should link WM811K Loc to LocDefect, not NearfullDefect."""
    nodes, edges, _summary = build_candidate_kg()
    nodes_path = tmp_path / "nodes_candidate.csv"
    edges_path = tmp_path / "edges_candidate.csv"
    export_kg_csv(nodes, edges, nodes_path=nodes_path, edges_path=edges_path)

    graph = KnowledgeGraph.from_paths(
        ["data/kg/nodes.csv", nodes_path],
        ["data/kg/edges.csv", "data/kg/mvtec_rca_reference.csv", edges_path],
        skip_missing=True,
    )
    candidates = graph.candidates("loc", scenario="wafer", top_k=3)

    assert candidates
    assert candidates[0].entity_id == "LocDefect"
    assert candidates[0].entity_id != "NearfullDefect"


def test_candidate_kg_artifacts_include_review_queue_and_coverage_report(
    tmp_path: Path,
) -> None:
    """Candidate KG build output should include review and coverage artifacts."""
    output = write_candidate_kg_artifacts(output_dir=tmp_path, overwrite=True)

    assert output.review_queue_path.is_file()
    assert output.coverage_report_path.is_file()
    with output.review_queue_path.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))
    coverage = json.loads(output.coverage_report_path.read_text(encoding="utf-8"))

    assert review_rows
    assert any(row["review_priority"] == "high" for row in review_rows)
    assert all("verified root cause" not in row["evidence"].lower() for row in review_rows)
    assert coverage["edge_counts_by_layer"]["candidate_mechanism"] > 0
    assert coverage["review_status_counts"]["auto"] > 0
    assert coverage["wm811k_pattern_coverage"] == [spec.pattern for spec in WAFER_PATTERNS]
