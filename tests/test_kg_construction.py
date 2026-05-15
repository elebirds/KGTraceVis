"""Tests for source-constrained KG construction helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
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
    load_source_library,
    load_source_registry,
    load_source_text,
    validate_candidate_claim_boundaries,
    validate_edges,
    write_candidate_kg_artifacts,
    write_end_to_end_interpretability_audit,
    write_source_library_manifest,
)
from kgtracevis.kg_construction.case_kg_hardening import WAFER_PATTERNS
from kgtracevis.kg_construction.export_kg_csv import EDGE_COLUMNS, NODE_COLUMNS
from kgtracevis.kg_construction.mvtec_source_bundle import (
    DownloadableSource,
    download_mvtec_source_bundle,
)
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


def test_source_library_loads_records_and_writes_safe_manifest(tmp_path: Path) -> None:
    """Source Library records should convert to construction sources without text leaks."""
    library_path = tmp_path / "source_library.json"
    library_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "inline_note",
                        "source_type": "txt",
                        "scenario": "shared",
                        "text": "Cooling alert can suggest pump seal wear.",
                        "metadata": {"owner": "unit"},
                        "provenance_policy": "source_grounded_candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    records = load_source_library(library_path)
    source = records[0].to_construction_source()
    manifest_path = write_source_library_manifest(tmp_path / "manifest.json", records)
    manifest = json.loads(manifest_path.read_text())
    manifest_payload = json.dumps(manifest, sort_keys=True)

    assert len(records) == 1
    assert source.source_id == "inline_note"
    assert source.source_type == "txt"
    assert source.text == "Cooling alert can suggest pump seal wear."
    assert source.metadata["owner"] == "unit"
    assert source.metadata["provenance_policy"] == "source_grounded_candidate"
    assert manifest["artifact_type"] == "source_library_manifest_v1"
    assert manifest["sources"][0]["has_text"] is True
    assert "Cooling alert can suggest pump seal wear" not in manifest_payload


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
        assert spec.signature_id in node_ids
        assert (
            f"{spec.node_id}|HAS_SPATIAL_SIGNATURE|{spec.signature_id}|wafer"
            in edge_ids
        )

    assert "LocDefect|HAS_PLAUSIBLE_CAUSE|GlueRemovalInsufficient|wafer" not in edge_ids
    mechanism_nodes = [node for node in nodes if node.label in {"RootCause", "CauseCategory"}]
    assert not [node.id for node in mechanism_nodes if node.id.endswith("Candidate")]
    assert not [node.name for node in mechanism_nodes if "candidate" in node.name.lower()]
    assert validate_candidate_claim_boundaries(edges) == []
    assert summary["wm811k_pattern_coverage"] == [spec.pattern for spec in WAFER_PATTERNS]


def test_wafer_sop_mechanisms_are_low_confidence_and_loc_isolated() -> None:
    """SOP-derived Nearfull mechanisms should not leak into the Loc pattern."""
    nodes, edges, _summary = build_candidate_kg()
    node_by_id = {node.id: node for node in nodes}
    edge_by_id = {edge.edge_id: edge for edge in edges}
    nearfull_targets = {
        "WetCleanResidue",
        "RinseFlowInsufficient",
        "MegasonicRinseInsufficient",
        "WaterQualityExcursion",
        "RecipeStepSkip",
    }

    for target in nearfull_targets:
        edge = edge_by_id[f"NearfullDefect|HAS_PLAUSIBLE_CAUSE|{target}|wafer"]
        assert edge.source == "wafer_factory_sop_private_summary"
        assert 0.42 <= edge.confidence <= 0.52
        assert edge.review_status == "auto"
        assert "Private SOP summary snippet:" in edge.evidence

    loc_forbidden_targets = nearfull_targets | {"GlueRemovalInsufficient"}
    for target in loc_forbidden_targets:
        assert f"LocDefect|HAS_PLAUSIBLE_CAUSE|{target}|wafer" not in edge_by_id
        assert (
            f"LocalClusterSignature|SUGGESTS_PLAUSIBLE_MECHANISM|{target}|wafer"
            not in edge_by_id
        )
    loc_process_edge = edge_by_id[
        "LocalClusterSignature|SUGGESTS_PLAUSIBLE_MECHANISM|ProcessNonuniformity|wafer"
    ]
    assert loc_process_edge.source == "wm811k_low_confidence_investigation_rule"

    nearfull_signature_edge = edge_by_id[
        "NearFullDenseSignature|SUGGESTS_PLAUSIBLE_MECHANISM|WaterQualityExcursion|wafer"
    ]
    assert nearfull_signature_edge.source == "wafer_factory_sop_private_summary"

    for node_id in nearfull_targets | {
        "ResistStripInsufficient",
        "ProcessInterruption",
        "WaferTransferMisalignment",
        "ChamberContamination",
    }:
        assert node_id in node_by_id
        assert "Candidate" not in node_id
        assert "candidate" not in node_by_id[node_id].name.lower()


def test_candidate_kg_adds_object_specific_mvtec_mechanisms(tmp_path: Path) -> None:
    """MVTec candidate KG should include object-specific explanation targets."""
    records_path = tmp_path / "mvtec_records.jsonl"
    records_path.write_text(
        "\n".join(
            [
                (
                    '{"case_id":"mvtec_cable_test_cut_outer_insulation_000",'
                    '"object":"cable","source_label":"cut_outer_insulation",'
                    '"defect_type":"cut_outer_insulation"}'
                ),
                (
                    '{"case_id":"mvtec_zipper_test_broken_teeth_000",'
                    '"object":"zipper","source_label":"broken_teeth",'
                    '"defect_type":"broken_teeth"}'
                ),
                (
                    '{"case_id":"mvtec_capsule_test_poke_000",'
                    '"object":"capsule","source_label":"poke",'
                    '"defect_type":"poke"}'
                ),
                (
                    '{"case_id":"mvtec_leather_test_poke_000",'
                    '"object":"leather","source_label":"poke",'
                    '"defect_type":"poke"}'
                ),
            ]
        ),
        encoding="utf-8",
    )

    nodes, edges, _summary = build_candidate_kg(mvtec_records_path=records_path)
    node_ids = {node.id for node in nodes}
    edge_by_id = {edge.edge_id: edge for edge in edges}

    assert "CableInsulationDamage" in node_ids
    assert "ZipperTeethAssembly" in node_ids
    cable_edge = edge_by_id[
        "CableObject|SUGGESTS_PLAUSIBLE_MECHANISM|"
        "CableInsulationDamage|mvtec"
    ]
    zipper_edge = edge_by_id[
        "ZipperObject|SUGGESTS_PLAUSIBLE_MECHANISM|ZipperTeethAssembly|mvtec"
    ]
    assert cable_edge.source == "mvtec_object_specific_visual_rule"
    assert zipper_edge.source == "mvtec_object_specific_visual_rule"
    assert "object-specific candidate investigation target" in cable_edge.evidence
    assert (
        "CutOuterInsulationDefect|HAS_PLAUSIBLE_CAUSE|"
        "CableInsulationDamage|mvtec"
        in edge_by_id
    )
    assert (
        "PokeDefect|HAS_PLAUSIBLE_CAUSE|CapsuleShellDamage|mvtec"
        not in edge_by_id
    )
    assert cable_edge.review_status == "auto"


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

    assert graph.has_edge(
        "NearfullDefect",
        "HAS_SPATIAL_SIGNATURE",
        "NearFullDenseSignature",
    )
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


def test_end_to_end_interpretability_audit_records_provenance(
    tmp_path: Path,
) -> None:
    """Strict audit should tie records, Evidence, overlay reasoning, and claims."""
    mvtec_records = tmp_path / "mvtec_records.jsonl"
    mvtec_records.write_text(
        json.dumps(
            {
                "dataset": "mvtec",
                "case_id": "mvtec_fixture_clean_scratch",
                "object": "bottle",
                "defect_type": "scratch",
                "location": "surface",
                "morphology": "linear",
                "severity": 0.18,
                "confidence": 0.86,
                "source_path": "fixtures/mvtec/bottle_clean_scratch.png",
                "mask_path": "fixtures/mvtec/bottle_clean_scratch_mask.png",
                "detector": {
                    "name": "mvtec_anomaly_predictor",
                    "backend": "amazon-patchcore",
                    "checkpoint": "fixtures/models/mvtec_bottle",
                    "model_source": "amazon-science/patchcore-inspection",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    wm811k_records = tmp_path / "wm811k_records.jsonl"
    wm811k_records.write_text(
        json.dumps(
            {
                "dataset": "wafer",
                "adapter": "wm811k",
                "case_id": "wm811k_fixture_clean_nearfull",
                "wafer_id": "W811K-0001",
                "failure_pattern": "Near-full",
                "zone": "wafer_surface",
                "morphology": "dense_particles",
                "defect_density": 0.72,
                "classification_confidence": 0.88,
                "wafer_map_path": "fixtures/wm811k/W811K-0001.npy",
                "annotation_type": "native_ground_truth",
                "source_table": "fixtures/wm811k/test.pkl",
                "source_row_index": 42,
                "classifier": {
                    "name": "wm811k_classifier",
                    "backend": "torch-resnet34",
                    "model_source": "radai-agent/radai-wm811k-defect-detection",
                    "model_file": "best_radai_resnet.pt",
                    "produces_root_cause": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mvtec_pipeline = run_adapter_pipeline(
        mvtec_records,
        tmp_path / "mvtec_adapter",
        dataset="mvtec",
        top_k=2,
    )
    wm811k_pipeline = run_adapter_pipeline(
        wm811k_records,
        tmp_path / "wm811k_adapter",
        dataset="wafer",
        top_k=2,
    )

    output = write_end_to_end_interpretability_audit(
        output_dir=tmp_path / "audit",
        mvtec_records_path=mvtec_records,
        mvtec_adapter_table_path=mvtec_pipeline.table_path,
        wm811k_record_paths=[wm811k_records],
        wm811k_adapter_table_paths=[wm811k_pipeline.table_path],
        top_k=2,
        top_n=1,
        commands_run=["uv run python scripts/run_end_to_end_interpretability_audit.py"],
    )

    summary = json.loads(output.summary_path.read_text(encoding="utf-8"))
    assert output.markdown_path.is_file()
    assert summary["strict_audit_passed"] is True
    assert summary["claim_boundary"].startswith("candidate/plausible explanation")
    assert summary["commands_run"]
    assert "--wm811k-table" in summary["equivalent_reproduction_commands"][0]
    assert str(wm811k_pipeline.table_path) in summary["equivalent_reproduction_commands"][0]
    assert summary["artifacts"]["candidate_nodes"].endswith("nodes_candidate.csv")
    assert {item["label"] for item in summary["datasets"]} == {"mvtec", "wm811k_1"}
    for dataset in summary["datasets"]:
        assert dataset["record_count"] > 0
        assert dataset["adapter_evidence_count"] > 0
        assert dataset["overlay_case_count"] > 0
        assert dataset["overlay_kg_node_paths"]
        assert dataset["overlay_kg_edge_paths"]
        assert dataset["raw_dataset_or_model_producer"]["produces_root_cause"] is False
        assert (
            dataset["raw_dataset_or_model_producer"]["producer_provenance_level"]
            == "model_producer_record"
        )


def test_end_to_end_interpretability_audit_checks_all_records(
    tmp_path: Path,
) -> None:
    """Strict audit should fail mixed JSONL files with incomplete later records."""
    mvtec_records = tmp_path / "mvtec_records.jsonl"
    mvtec_records.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "dataset": "mvtec",
                        "case_id": "mvtec_real_shape_1",
                        "object": "bottle",
                        "defect_type": "scratch",
                        "source_path": "runs/mvtec/input/bottle/000.png",
                        "detector": {
                            "name": "mvtec_anomaly_predictor",
                            "backend": "amazon-patchcore",
                            "checkpoint": "runs/models/mvtec_bottle",
                        },
                    }
                ),
                json.dumps(
                    {
                        "dataset": "mvtec",
                        "case_id": "mvtec_incomplete_later_record",
                        "object": "bottle",
                        "defect_type": "scratch",
                        "image_path": "fixtures/mvtec/incomplete.png",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    wm811k_records = tmp_path / "wm811k_records.jsonl"
    wm811k_records.write_text(
        json.dumps(
            {
                "dataset": "wafer",
                "adapter": "wm811k",
                "case_id": "wm811k_real_shape_1",
                "wafer_id": "row-1",
                "failure_pattern": "Loc",
                "source_table": "runs/real_model_pipeline/assets/wm811k/input_tables/test.pkl",
                "source_row_index": 1,
                "classifier": {
                    "name": "wm811k_classifier",
                    "backend": "torch-resnet34",
                    "model_source": "radai-agent/radai-wm811k-defect-detection",
                    "model_file": "best_radai_resnet.pt",
                    "produces_root_cause": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mvtec_pipeline = run_adapter_pipeline(
        mvtec_records,
        tmp_path / "mvtec_adapter",
        dataset="mvtec",
        top_k=2,
    )
    wm811k_pipeline = run_adapter_pipeline(
        wm811k_records,
        tmp_path / "wm811k_adapter",
        dataset="wafer",
        top_k=2,
    )

    output = write_end_to_end_interpretability_audit(
        output_dir=tmp_path / "audit",
        mvtec_records_path=mvtec_records,
        mvtec_adapter_table_path=mvtec_pipeline.table_path,
        wm811k_record_paths=[wm811k_records],
        wm811k_adapter_table_paths=[wm811k_pipeline.table_path],
        top_k=2,
        top_n=1,
    )

    summary = json.loads(output.summary_path.read_text(encoding="utf-8"))
    mvtec = next(item for item in summary["datasets"] if item["label"] == "mvtec")
    producer = mvtec["raw_dataset_or_model_producer"]
    assert summary["strict_audit_passed"] is False
    assert producer["incomplete_record_count"] == 1
    assert producer["incomplete_case_id_samples"] == ["mvtec_incomplete_later_record"]
    assert any("not a strict model-producer record" in item for item in summary["strict_findings"])


def test_end_to_end_interpretability_audit_flags_fixture_records(
    tmp_path: Path,
) -> None:
    """Example records can be audited, but should not count as strict model evidence."""
    mvtec_pipeline = run_adapter_pipeline(
        "data/examples/records/mvtec_records.jsonl",
        tmp_path / "mvtec_adapter",
        dataset="mvtec",
        top_k=2,
    )
    wm811k_pipeline = run_adapter_pipeline(
        "data/examples/records/wm811k_records.jsonl",
        tmp_path / "wm811k_adapter",
        dataset="wafer",
        top_k=2,
    )

    output = write_end_to_end_interpretability_audit(
        output_dir=tmp_path / "audit",
        mvtec_records_path="data/examples/records/mvtec_records.jsonl",
        mvtec_adapter_table_path=mvtec_pipeline.table_path,
        wm811k_record_paths=["data/examples/records/wm811k_records.jsonl"],
        wm811k_adapter_table_paths=[wm811k_pipeline.table_path],
        top_k=2,
        top_n=1,
    )

    summary = json.loads(output.summary_path.read_text(encoding="utf-8"))
    assert summary["strict_audit_passed"] is False
    assert any("not a strict model-producer record" in item for item in summary["strict_findings"])


def test_mvtec_source_bundle_downloads_local_sources(tmp_path: Path) -> None:
    """Source bundle downloader should write files, manifest, and raw gitignore."""
    source_file = tmp_path / "source.html"
    source_file.write_text("<html>MVTec source</html>", encoding="utf-8")
    manifest = download_mvtec_source_bundle(
        tmp_path / "bundle",
        sources=[
            DownloadableSource(
                source_id="local_mvtec_source",
                title="Local MVTec source",
                url=source_file.as_uri(),
                filename="local.html",
                source_type="test_source",
                used_for="unit test",
            ),
            DownloadableSource(
                source_id="local_mvtec_binary_source",
                title="Local MVTec binary source",
                url=source_file.as_uri(),
                filename="raw/local.pdf",
                source_type="test_binary_source",
                used_for="unit test optional binary",
                binary=True,
            ),
        ],
    )

    output_dir = Path(str(manifest["output_dir"]))
    assert (output_dir / "local.html").read_text(encoding="utf-8") == (
        "<html>MVTec source</html>"
    )
    assert (output_dir / "manifest.json").is_file()
    source_records = manifest["sources"]
    assert isinstance(source_records, list)
    assert source_records[0]["status"] == "downloaded"
    assert source_records[1]["status"] == "skipped_binary"
    assert not (output_dir / "raw" / "local.pdf").exists()
    assert (output_dir / "README.md").is_file()
    assert (output_dir / "raw" / ".gitignore").read_text(encoding="utf-8") == (
        "*\n!.gitignore\n"
    )
