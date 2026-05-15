"""Tests for the reusable source-to-KG construction pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from kgtracevis.kg_construction import (
    GENERIC_PROFILE,
    CandidateEntity,
    CandidateTriple,
    DraftEntity,
    DraftKG,
    DraftRelation,
    ExtractorRegistry,
    KGConstructionSource,
    LLMDocumentIEExtractor,
    TepRcaGraphExtractor,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    build_publish_snapshot,
    build_review_queue,
    clean_candidate_nodes,
    clean_candidate_triples,
    clean_kg_edges,
    clean_kg_nodes,
    draft_status_to_review_status,
    run_entity_alignment,
    run_kg_construction,
    tep_external_id_to_kg_id,
)
from kgtracevis.kg_construction.extractors.structured import StructuredRecordExtractor


class UnitExtractor:
    """Small test extractor used to exercise the construction runner."""

    name = "unit"
    version = "v1"
    supported_source_types = ("unit",)

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Return one node pair and one relation."""
        return DraftKG(
            entities=(
                DraftEntity(
                    draft_id="entity-1",
                    source_id=source.source_id,
                    extractor_name=self.name,
                    extractor_version=self.version,
                    scenario=source.scenario,
                    entity_id_suggestion="UnitSource",
                    name="Unit source",
                    label="Variable",
                    aliases=("unit source",),
                    evidence="source row",
                ),
                DraftEntity(
                    draft_id="entity-2",
                    source_id=source.source_id,
                    extractor_name=self.name,
                    extractor_version=self.version,
                    scenario=source.scenario,
                    entity_id_suggestion="UnitTarget",
                    name="Unit target",
                    label="ProcessUnit",
                    evidence="source row",
                ),
            ),
            relations=(
                DraftRelation(
                    draft_id="relation-1",
                    source_id=source.source_id,
                    extractor_name=self.name,
                    extractor_version=self.version,
                    scenario=source.scenario,
                    head="UnitSource",
                    relation="BELONGS_TO",
                    tail="UnitTarget",
                    evidence="source row",
                    confidence=0.73,
                    status="accepted",
                ),
            ),
        )


class FakeDocumentIEClient:
    """Small document IE fake for pipeline-level document source tests."""

    def extract_candidates(
        self,
        chunk: Any,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Return one source-grounded candidate graph."""
        return {
            "entities": [
                {
                    "id": "PumpFault",
                    "name": "Pump fault",
                    "label": "FaultEvent",
                    "evidence": "Pump fault can indicate seal wear.",
                    "confidence": 0.62,
                },
                {
                    "id": "SealWear",
                    "name": "Seal wear",
                    "label": "RootCause",
                    "evidence": "seal wear",
                    "confidence": 0.62,
                },
            ],
            "relations": [
                {
                    "head": "PumpFault",
                    "relation": "SUGGESTS_ROOT_CAUSE",
                    "tail": "SealWear",
                    "evidence": "Pump fault can indicate seal wear.",
                    "confidence": 0.55,
                }
            ],
        }


class ParserAwareUnitExtractor:
    """Extractor that proves parsed source content is the primary input."""

    name = "parser_aware_unit"
    version = "v1"
    supported_source_types = ("unit",)

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Legacy extraction path should not be used when parsed input is supported."""
        raise AssertionError(f"legacy extract should not run for {source.source_id}")

    def extract_from_parsed(self, parsed: Any, *, source: KGConstructionSource) -> DraftKG:
        """Return a small DraftKG from parser output."""
        assert parsed.source_id == source.source_id
        assert parsed.kind == "source_reference"
        return UnitExtractor().extract(source)


def test_run_kg_construction_uses_registered_extractors() -> None:
    """The construction runner should build validated KG rows from drafts."""
    result = run_kg_construction(
        [KGConstructionSource(source_id="unit_source", source_type="unit", scenario="tep")],
        registry=ExtractorRegistry([UnitExtractor()]),
        run_id="kgbuild_unit",
    )

    assert result.run_id == "kgbuild_unit"
    assert result.summary["source_ids"] == ["unit_source"]
    assert result.summary["draft_entity_count"] == 2
    assert result.summary["draft_relation_count"] == 1
    assert result.build_summary.review_status_counts == {"reviewed": 1}
    assert [node.id for node in result.nodes] == ["UnitSource", "UnitTarget"]
    assert len(result.edges) == 1
    assert result.edges[0].source == "unit_source"
    assert result.edges[0].review_status == "reviewed"
    assert result.edges[0].weight == 0.27


def test_run_kg_construction_prefers_parser_output_extractors() -> None:
    """Parser-aware extractors should consume ParsedSourceContent before legacy source IO."""
    result = run_kg_construction(
        [KGConstructionSource(source_id="parser_unit", source_type="unit", scenario="tep")],
        registry=ExtractorRegistry([ParserAwareUnitExtractor()]),
        run_id="kgbuild_parser_aware",
    )

    assert result.run_id == "kgbuild_parser_aware"
    assert result.parsed_sources[0].kind == "source_reference"
    assert result.summary["extractor_versions"] == {"parser_aware_unit": "v1"}
    assert len(result.nodes) == 2
    assert len(result.edges) == 1


def test_run_kg_construction_validates_extractor_before_parse() -> None:
    """Parser audit should not change missing-extractor failure behavior."""
    with pytest.raises(ValueError, match="no KG source extractor registered"):
        run_kg_construction(
            [KGConstructionSource(source_id="note", source_type="txt", scenario="tep")]
        )


def test_run_kg_construction_records_structured_parse_audit(tmp_path: Path) -> None:
    """Structured/manual sources should report parser metadata and row counts."""
    source_path = tmp_path / "toy_source.jsonl"
    _write_jsonl(
        source_path,
        [
            {
                "id": "ToyRoot",
                "name": "Toy root",
                "label": "RootCause",
                "scenario": "shared",
                "evidence": "toy row 1",
            },
            {
                "id": "ToyObservation",
                "name": "Toy observation",
                "label": "Observation",
                "scenario": "shared",
                "evidence": "toy row 2",
            },
            {
                "head": "ToyRoot",
                "relation": "CAUSES",
                "tail": "ToyObservation",
                "scenario": "shared",
                "evidence": "toy row 3",
                "confidence": 0.81,
            },
        ],
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="toy_manual_source",
                source_type="manual_table",
                scenario="shared",
                path=source_path,
            )
        ],
        run_id="kgbuild_toy_parse_audit",
    )

    manifest = result.audit_graph.manifest()
    parsed_source = manifest["parsed_sources"][0]
    assert manifest["parsed_source_count"] == 1
    assert parsed_source["kind"] == "rows"
    assert parsed_source["parser_kind"] == "manual_table"
    assert parsed_source["row_count"] == 3
    assert parsed_source["chunk_count"] == 0
    assert parsed_source["source_reference"] == str(source_path)
    assert parsed_source["safe_source"]["path"] == str(source_path)
    assert parsed_source["safe_source"]["path_kind"] == "file"
    assert "evidence" in parsed_source["parser_metadata"]["columns"]


def test_structured_extractor_consumes_parser_rows_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured pipeline extraction should use parser rows instead of reloading files."""
    source_path = tmp_path / "toy_source.jsonl"
    _write_jsonl(
        source_path,
        [
            {
                "id": "SingleParseEvent",
                "name": "Single parse event",
                "label": "Event",
                "scenario": "shared",
                "evidence": "single parse row",
            },
            {
                "id": "SingleParseRoot",
                "name": "Single parse root",
                "label": "RootCause",
                "scenario": "shared",
                "evidence": "single parse root row",
            },
            {
                "head": "SingleParseEvent",
                "relation": "SUGGESTS_ROOT_CAUSE",
                "tail": "SingleParseRoot",
                "scenario": "shared",
                "evidence": "single parse event suggests single parse root",
                "confidence": 0.7,
            },
        ],
    )

    def fail_if_extractor_reloads(path: Path) -> list[dict[str, object]]:
        raise AssertionError(f"extractor reloaded structured rows from {path}")

    monkeypatch.setattr(
        "kgtracevis.kg_construction.extractors.structured.load_structured_records",
        fail_if_extractor_reloads,
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="single_parse_structured",
                source_type="manual_table",
                scenario="shared",
                path=source_path,
            )
        ],
        registry=ExtractorRegistry([StructuredRecordExtractor()]),
        run_id="kgbuild_single_parse_structured",
    )

    assert result.summary["draft_entity_count"] == 2
    assert result.summary["draft_relation_count"] == 1
    assert result.edges[0].source == "single_parse_structured"


def test_run_kg_construction_records_document_parse_audit_without_text() -> None:
    """Document parse summaries should keep chunk metadata but not source text."""
    source_text = "Pump fault can indicate seal wear. Operators noted vibration."

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="pump_manual",
                source_type="txt",
                scenario="tep",
                text=source_text,
            )
        ],
        registry=ExtractorRegistry([LLMDocumentIEExtractor(FakeDocumentIEClient())]),
        run_id="kgbuild_document_parse_audit",
    )

    manifest = result.audit_graph.manifest()
    parsed_source = manifest["parsed_sources"][0]
    parsed_payload = json.dumps(parsed_source, sort_keys=True)
    assert parsed_source["kind"] == "text_chunks"
    assert parsed_source["parser_kind"] == "text"
    assert parsed_source["row_count"] == 0
    assert parsed_source["chunk_count"] == 1
    assert parsed_source["safe_source"] == {
        "source_id": "pump_manual",
        "source_type": "txt",
        "scenario": "tep",
        "has_text": True,
    }
    assert parsed_source["parser_metadata"]["chunk_ids"][0].startswith(
        "pump_manual:chunk:0001:"
    )
    assert parsed_source["parser_metadata"]["chunk_char_ranges"] == [
        {
            "chunk_id": parsed_source["parser_metadata"]["chunk_ids"][0],
            "start_char": 0,
            "end_char": len(source_text),
        }
    ]
    assert source_text not in parsed_payload
    assert "Pump fault can indicate seal wear" not in parsed_payload
    assert len(result.nodes) == 2
    assert len(result.edges) == 1


def test_kg_construction_result_builds_manifest() -> None:
    """Construction results expose typed manifest and draft-row DTOs."""
    result = run_kg_construction(
        [KGConstructionSource(source_id="unit_source", source_type="unit", scenario="tep")],
        registry=ExtractorRegistry([UnitExtractor()]),
        run_id="kgbuild_manifest",
    )

    manifest = result.manifest(
        artifact_paths={
            "nodes": "runs/source_kg_build/nodes.csv",
            "edges": "runs/source_kg_build/edges.csv",
        }
    )

    assert manifest.artifact_type == "source_to_kg_construction_manifest_v1"
    assert manifest.run.run_id == "kgbuild_manifest"
    assert manifest.summary.node_count == 2
    assert manifest.summary.kg_build_id == "kgbuild_manifest"
    assert manifest.summary.extractor_versions == {"unit": "v1"}
    assert manifest.summary.profile_version == "tep_rca_v1"
    assert manifest.summary.review_policy
    assert manifest.artifacts["nodes"].endswith("nodes.csv")
    assert [row.row_type for row in manifest.draft_rows] == ["entity", "entity", "relation"]
    relation_row = manifest.draft_rows[-1]
    assert relation_row.target_key == "relation:relation-1"
    assert relation_row.kg_payload["head"] == "UnitSource"
    assert relation_row.kg_payload["source"] == "unit_source"
    assert relation_row.kg_payload["review_status"] == "reviewed"


def test_draft_status_maps_to_kg_review_status() -> None:
    """Draft statuses should map to the existing KG CSV review vocabulary."""
    assert draft_status_to_review_status("draft") == "auto"
    assert draft_status_to_review_status("accepted") == "reviewed"
    assert draft_status_to_review_status("published") == "reviewed"
    assert draft_status_to_review_status("rejected") == "rejected"


def test_alignment_manifest_and_review_queue_cover_entity_decisions() -> None:
    """Alignment should expose canonical rows and all entity decisions for review."""
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity:pump-a",
                source_id="alignment_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpA",
                name="Feed pump",
                label="Equipment",
                aliases=("asset:alias_a",),
                evidence="pump A source row",
                confidence=0.9,
            ),
            DraftEntity(
                draft_id="entity:pump-b",
                source_id="alignment_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpB",
                name="Feed pump",
                label="Equipment",
                evidence="duplicate pump source row",
                confidence=0.87,
            ),
            DraftEntity(
                draft_id="entity:motor-d",
                source_id="alignment_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="MotorD",
                name="Drive motor",
                label="Equipment",
                aliases=("asset:alias_b",),
                evidence="motor source row",
                confidence=0.88,
            ),
            DraftEntity(
                draft_id="entity:conflict-c",
                source_id="alignment_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="ConflictC",
                name="Conflicting equipment",
                label="Equipment",
                aliases=("asset:alias_a", "asset:alias_b"),
                evidence="conflicting aliases source row",
                confidence=0.72,
            ),
            DraftEntity(
                draft_id="entity:unknown",
                source_id="alignment_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="",
                name="Mystery equipment",
                label="Equipment",
                evidence="unresolved source row",
                confidence=0.5,
            ),
        )
    )

    alignment = run_entity_alignment(draft, GENERIC_PROFILE)
    manifest = alignment.manifest()
    review_queue = build_review_queue((), alignment=alignment)
    queue_by_type = {item.item_type: item for item in review_queue}

    assert manifest["artifact_type"] == "entity_alignment_manifest_v1"
    assert manifest["canonical_entity_count"] == 2
    assert manifest["merge_candidate_count"] == 2
    assert manifest["unresolved_entity_count"] == 1
    assert manifest["conflict_count"] == 1
    pump_entry = next(
        entry
        for entry in manifest["canonical_entities"]
        if entry["canonical_id"] == "PumpA"
    )
    assert pump_entry["source_entity_ids"] == ["ConflictC", "PumpA", "PumpB"]
    assert "pump A source row" in pump_entry["evidence_refs"]
    assert queue_by_type["entity_alignment_conflict"].recommended_action == (
        "resolve_conflict"
    )
    assert queue_by_type["entity_merge_candidate"].recommended_action == (
        "confirm_or_split_merge"
    )
    assert queue_by_type["unresolved_entity"].recommended_action == (
        "assign_canonical_entity"
    )
    assert all(item.reason and item.priority > 0 for item in review_queue)
    assert {item.review_status for item in review_queue} == {"auto"}
    assert json.loads(json.dumps(manifest))["canonical_entities"] == (
        manifest["canonical_entities"]
    )


def test_draft_rows_convert_directly_to_kg_rows_with_rca_metadata() -> None:
    """Draft-to-KG conversion should preserve RCA metadata without candidate bridge."""
    entity = DraftEntity(
        draft_id="entity-component-a",
        source_id="unit_source",
        extractor_name="unit",
        extractor_version="v1",
        scenario="tep",
        entity_id_suggestion="component_a",
        canonical_id="ComponentA",
        name="Component A",
        label="Component",
        aliases=("component:a",),
        description="RCA component anchor",
        evidence="node evidence",
    )
    relation = DraftRelation(
        draft_id="relation-component-fault",
        source_id="unit_source",
        extractor_name="unit",
        extractor_version="v1",
        scenario="tep",
        head="component_a",
        relation="causes",
        tail="fault_06",
        evidence="edge evidence",
        confidence=0.71,
        status="accepted",
        metadata={
            "relation_family": "FAULT_SOURCE",
            "propagation_enabled": "true",
            "propagation_direction": "reverse",
            "propagation_priority": "0.8",
            "attenuation": "0.6",
            "edge_weight": "0.12",
            "root_candidate": "true",
            "observable": True,
            "event_anchor": "event:fault_06",
            "fault_anchor": "fault_anchor:fault_06",
            "task_view": "root_kgd_view",
            "confidence_policy": "curated_bridge",
            "external_edge_id": "rca_edge_1",
            "kg_build_id": "kgbuild_existing",
        },
    )

    node = entity.to_kg_node()
    edge = relation.to_kg_edge()
    cleaned_nodes = clean_kg_nodes([node])
    cleaned_edges = clean_kg_edges([edge])

    assert node.id == "ComponentA"
    assert cleaned_nodes[0].id == "ComponentA"
    assert edge.relation_family == "FAULT_SOURCE"
    assert edge.propagation_enabled is True
    assert edge.propagation_direction == "reverse"
    assert edge.propagation_priority == 0.8
    assert edge.attenuation == 0.6
    assert edge.edge_weight == 0.12
    assert edge.root_candidate is True
    assert edge.observable is True
    assert edge.event_anchor == "event:fault_06"
    assert edge.fault_anchor == "fault_anchor:fault_06"
    assert edge.task_view == "root_kgd_view"
    assert edge.confidence_policy == "curated_bridge"
    assert edge.external_edge_id == "rca_edge_1"
    assert edge.kg_build_id == "kgbuild_existing"
    assert cleaned_edges[0].relation == "CAUSES"
    assert cleaned_edges[0].weight == 0.29


def test_legacy_candidate_api_matches_direct_draft_conversion() -> None:
    """Candidate bridge methods should keep old callers compatible."""
    entity = DraftEntity(
        draft_id="entity-unit",
        source_id="legacy_source",
        extractor_name="unit",
        extractor_version="v1",
        scenario="tep",
        entity_id_suggestion="UnitNode",
        name="Unit node",
        label="Variable",
        aliases=("unit",),
        evidence="node evidence",
    )
    relation = DraftRelation(
        draft_id="relation-unit",
        source_id="legacy_source",
        extractor_name="unit",
        extractor_version="v1",
        scenario="tep",
        head="UnitNode",
        relation="OBSERVED_BY",
        tail="SensorNode",
        evidence="edge evidence",
        confidence=0.82,
        metadata={
            "relation_family": "OBSERVATION",
            "propagation_enabled": True,
            "external_edge_id": "legacy_edge",
        },
    )

    legacy_entity = entity.to_candidate_entity()
    legacy_triple = relation.to_candidate_triple()

    assert isinstance(legacy_entity, CandidateEntity)
    assert isinstance(legacy_triple, CandidateTriple)
    assert clean_candidate_nodes([legacy_entity]) == clean_kg_nodes([entity.to_kg_node()])
    assert clean_candidate_triples([legacy_triple]) == clean_kg_edges([relation.to_kg_edge()])
    assert legacy_triple.external_edge_id == "legacy_edge"


def test_tep_external_id_to_kg_id_is_pascal_case() -> None:
    """TEP external IDs should map into KGTraceVis-compatible node IDs."""
    assert tep_external_id_to_kg_id("variable:xmeas_1", label="Variable") == "Xmeas1Variable"
    assert (
        tep_external_id_to_kg_id("stream:stream_1_a_feed", label="Stream")
        == "Stream1AFeedStream"
    )


def test_tep_semantic_lift_extractor_imports_runtime_graph(tmp_path: Path) -> None:
    """TEP semantic-lift JSONL rows should become scenario-scoped KG rows."""
    nodes_path = tmp_path / "semantic_lift_nodes.jsonl"
    edges_path = tmp_path / "semantic_lift_edges.jsonl"
    _write_jsonl(
        nodes_path,
        [
            {
                "node_id": "stream:stream_1_a_feed",
                "entity_id": "stream:stream_1_a_feed",
                "entity_type": "Stream",
                "name": "Stream 1 A feed",
                "aliases": ["A feed"],
                "provenance_ids": ["ev_stream"],
            },
            {
                "node_id": "variable:xmeas_1",
                "entity_id": "variable:xmeas_1",
                "entity_type": "Variable",
                "name": "XMEAS_1 (A Feed)",
                "aliases": ["Plant Output 1"],
                "provenance_ids": ["ev_xmeas"],
                "tep_channel": "xmeas_1",
                "variable_role": "sensor",
            },
        ],
    )
    _write_jsonl(
        edges_path,
        [
            {
                "edge_id": "semantic_lift_edge_1",
                "head_id": "stream:stream_1_a_feed",
                "relation": "OBSERVED_BY",
                "tail_id": "variable:xmeas_1",
                "confidence": 0.82,
                "relation_family": "OBSERVATION",
                "propagation_enabled": True,
                "provenance_ids": ["ev_edge"],
                "support_triple_ids": ["triple_1"],
                "raw_relations": ["measures_flow_of"],
            }
        ],
    )

    registry = ExtractorRegistry([TepSemanticLiftExtractor()])
    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_semantic_lift_unit",
                source_type="tep_semantic_lift",
                scenario="tep",
                metadata={"nodes_path": nodes_path, "edges_path": edges_path},
            )
        ],
        registry=registry,
    )

    assert [node.id for node in result.nodes] == ["Stream1AFeedStream", "Xmeas1Variable"]
    assert result.nodes[1].aliases == ("variable:xmeas_1", "xmeas_1")
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.head == "Stream1AFeedStream"
    assert edge.relation == "OBSERVED_BY"
    assert edge.tail == "Xmeas1Variable"
    assert edge.scenario == "tep"
    assert edge.source == "tep_semantic_lift_unit"
    assert edge.review_status == "auto"
    assert "relation_family=OBSERVATION" in edge.evidence
    assert "support_triple_ids=triple_1" in edge.evidence
    assert result.draft.relations[0].metadata["propagation_enabled"] is True
    assert result.alignment.manifest()["alignment_relation_count"] == 0
    assert result.alignment.manifest()["canonical_entities"][0]["external_ids"] == [
        "stream:stream_1_a_feed",
    ]
    assert result.semantic_layer.manifest["skipped_relation_count"] == 0


def test_tep_source_reference_parse_audit_reports_paths(tmp_path: Path) -> None:
    """TEP source-reference inputs should preserve safe path provenance."""
    nodes_path = tmp_path / "semantic_lift_nodes.jsonl"
    edges_path = tmp_path / "semantic_lift_edges.jsonl"
    _write_jsonl(
        nodes_path,
        [
            {
                "node_id": "stream:stream_1_a_feed",
                "entity_id": "stream:stream_1_a_feed",
                "entity_type": "Stream",
                "name": "Stream 1 A feed",
            }
        ],
    )
    _write_jsonl(edges_path, [])

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_semantic_lift_unit",
                source_type="tep_semantic_lift",
                scenario="tep",
                metadata={"nodes_path": nodes_path, "edges_path": edges_path},
            )
        ],
        registry=ExtractorRegistry([TepSemanticLiftExtractor()]),
        run_id="kgbuild_tep_parse_audit",
    )

    parsed_source = result.audit_graph.manifest()["parsed_sources"][0]
    assert parsed_source["kind"] == "source_reference"
    assert parsed_source["parser_kind"] == "source_reference"
    assert parsed_source["row_count"] == 0
    assert parsed_source["chunk_count"] == 0
    assert f"nodes_path={nodes_path}" in parsed_source["source_reference"]
    assert f"edges_path={edges_path}" in parsed_source["source_reference"]
    assert parsed_source["safe_source"]["metadata_paths"] == {
        "edges_path": str(edges_path),
        "nodes_path": str(nodes_path),
    }
    assert parsed_source["parser_metadata"]["paths"] == {
        "edges_path": str(edges_path),
        "nodes_path": str(nodes_path),
    }


def test_tep_variable_mapping_extractor_imports_channel_aliases(tmp_path: Path) -> None:
    """TEP variable mapping rows should create variable nodes and alignment edges."""
    mapping_path = tmp_path / "tep_variable_mapping.jsonl"
    _write_jsonl(
        mapping_path,
        [
            {
                "tep_channel": "xmv_1",
                "sequence_column": "xmv_1",
                "kg_entity_id": "variable:manipulated_variable_1_d_feed",
                "alternate_entity_ids": "variable:mv_42",
                "mapping_source": "explicit_rule_mv_plus_prior_mv_alignment",
                "notes": "xmv_1 maps to MV_42 through explicit table.",
            }
        ],
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_variable_mapping_unit",
                source_type="tep_variable_mapping",
                scenario="tep",
                path=mapping_path,
            )
        ],
        registry=ExtractorRegistry([TepVariableMappingExtractor()]),
    )

    assert [node.id for node in result.nodes] == [
        "ManipulatedVariable1DFeedVariable",
        "Mv42Variable",
    ]
    assert result.nodes[0].aliases == (
        "variable:manipulated_variable_1_d_feed",
        "xmv_1",
    )
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.head == "Mv42Variable"
    assert edge.relation == "ALIGNS_TO"
    assert edge.tail == "ManipulatedVariable1DFeedVariable"
    assert edge.confidence == 0.96
    assert "mapping_source=explicit_rule_mv_plus_prior_mv_alignment" in edge.evidence
    assert result.alignment.manifest()["alignment_relation_count"] == 0
    assert result.semantic_layer.manifest["skipped_relation_count"] == 0


def test_tep_variable_mapping_consumes_parser_rows_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEP variable mapping extraction should use parsed rows instead of reloading."""
    mapping_path = tmp_path / "tep_variable_mapping.jsonl"
    _write_jsonl(
        mapping_path,
        [
            {
                "tep_channel": "xmeas_1",
                "sequence_column": "xmeas_1",
                "kg_entity_id": "variable:a_feed_stream",
                "alternate_entity_ids": "",
                "mapping_source": "explicit_table",
            }
        ],
    )

    def fail_if_extractor_reloads(path: Path) -> list[dict[str, object]]:
        raise AssertionError(f"extractor reloaded TEP mapping rows from {path}")

    monkeypatch.setattr(
        "kgtracevis.kg_construction.tep_import._read_records",
        fail_if_extractor_reloads,
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_variable_mapping_single_parse",
                source_type="tep_variable_mapping",
                scenario="tep",
                path=mapping_path,
            )
        ],
        registry=ExtractorRegistry([TepVariableMappingExtractor()]),
        run_id="kgbuild_tep_mapping_single_parse",
    )

    assert result.parsed_sources[0].kind == "rows"
    assert result.summary["extractor_versions"] == {"tep_variable_mapping": "v1"}
    assert [node.id for node in result.nodes] == ["AFeedStreamVariable"]


def test_tep_import_preserves_alignment_alias_nodes(tmp_path: Path) -> None:
    """TEP entity-resolution members should not collapse explicit alignment nodes."""
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
    _write_jsonl(
        semantic_dir / "semantic_lift_nodes.jsonl",
        [
            {
                "node_id": "variable:manipulated_variable_1_d_feed",
                "entity_id": "variable:manipulated_variable_1_d_feed",
                "entity_type": "Variable",
                "name": "Manipulated Variable 1: D feed",
                "full_kg_entity_ids": [
                    "signalnode:xmv1",
                    "variable:manipulated_variable_1_d_feed",
                    "variable:mv_42",
                ],
                "tep_channel": "xmv_1",
            }
        ],
    )
    _write_jsonl(semantic_dir / "semantic_lift_edges.jsonl", [])
    mapping_path = tmp_path / "tep_variable_mapping.jsonl"
    _write_jsonl(
        mapping_path,
        [
            {
                "tep_channel": "xmv_1",
                "sequence_column": "xmv_1",
                "kg_entity_id": "variable:manipulated_variable_1_d_feed",
                "alternate_entity_ids": "variable:mv_42",
                "mapping_source": "explicit_rule_mv_plus_prior_mv_alignment",
            }
        ],
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_semantic_lift_unit",
                source_type="tep_semantic_lift",
                scenario="tep",
                path=semantic_dir,
            ),
            KGConstructionSource(
                source_id="tep_variable_mapping_unit",
                source_type="tep_variable_mapping",
                scenario="tep",
                path=mapping_path,
            ),
        ],
        registry=ExtractorRegistry([TepSemanticLiftExtractor(), TepVariableMappingExtractor()]),
    )

    nodes_by_id = {node.id: node for node in result.nodes}
    assert "ManipulatedVariable1DFeedVariable" in nodes_by_id
    assert "Mv42Variable" in nodes_by_id
    assert "variable:mv_42" not in nodes_by_id["ManipulatedVariable1DFeedVariable"].aliases
    assert result.edges[0].head == "Mv42Variable"
    assert result.edges[0].tail == "ManipulatedVariable1DFeedVariable"


def test_tep_rca_graph_extractor_preserves_rca_metadata(tmp_path: Path) -> None:
    """TEP RCA graph rows should become RCA-view edges with propagation metadata."""
    rca_dir = tmp_path / "rca"
    rca_dir.mkdir()
    _write_jsonl(
        rca_dir / "nodes.jsonl",
        [
            {
                "node_id": "component:component_a",
                "entity_id": "component:component_a",
                "entity_type": "Component",
                "name": "Component A",
                "candidate_role": "composition_anchor",
                "root_cause_candidate": True,
                "provenance_ids": ["ev_component"],
            },
            {
                "node_id": "fault_anchor:fault_06",
                "entity_id": "fault_anchor:fault_06",
                "entity_type": "FaultAnchor",
                "name": "Fault 06 anchor",
                "candidate_role": "fault_anchor",
                "provenance_ids": ["ev_fault"],
            },
        ],
    )
    _write_jsonl(
        rca_dir / "edges.jsonl",
        [
            {
                "edge_id": "rca_edge_1",
                "head_id": "component:component_a",
                "relation": "CAUSES",
                "tail_id": "fault_anchor:fault_06",
                "confidence": 0.71,
                "relation_family": "FAULT_SOURCE",
                "propagation_enabled": True,
                "edge_origin": "curated_bridge",
                "review_status": "accept",
                "provenance_ids": ["ev_edge"],
            }
        ],
    )

    result = run_kg_construction(
        [
            KGConstructionSource(
                source_id="tep_rca_graph_unit",
                source_type="tep_rca_graph",
                scenario="tep",
                path=rca_dir,
            )
        ],
        registry=ExtractorRegistry([TepRcaGraphExtractor()]),
        run_id="kgbuild_tep_rca_unit",
    )

    assert result.rca_view.manifest["task_view"] == "root_kgd_view"
    assert result.rca_view.manifest["propagation_edge_count"] == 1
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.relation == "CAUSES"
    assert edge.relation_family == "FAULT_SOURCE"
    assert edge.propagation_enabled is True
    assert edge.review_status == "auto"
    assert edge.external_edge_id == "rca_edge_1"
    assert edge.kg_build_id == "kgbuild_tep_rca_unit"
    assert result.draft.relations[0].metadata["tep_review_status"] == "accept"
    assert result.review_queue[0].priority >= 80
    snapshot = build_publish_snapshot(
        kg_build_id="kgbuild_tep_rca_unit",
        nodes=result.nodes,
        edges=result.edges,
    )
    assert snapshot.edges == ()
    assert snapshot.report_payload()["disposition_counts"] == {"pending_review": 1}
    assert snapshot.report_items[0].reason == (
        "high-risk causal/propagation/document edge requires review"
    )


def test_build_source_kg_script_writes_candidate_artifacts(tmp_path: Path) -> None:
    """The source-to-KG CLI should write candidate CSV and summary artifacts."""
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
    rca_dir = tmp_path / "rca"
    rca_dir.mkdir()
    _write_jsonl(
        semantic_dir / "semantic_lift_nodes.jsonl",
        [
            {
                "node_id": "stream:steam",
                "entity_id": "stream:steam",
                "entity_type": "Stream",
                "name": "Steam",
                "provenance_ids": ["ev_steam"],
            },
            {
                "node_id": "variable:xmeas_19",
                "entity_id": "variable:xmeas_19",
                "entity_type": "Variable",
                "name": "XMEAS_19",
                "provenance_ids": ["ev_xmeas_19"],
                "tep_channel": "xmeas_19",
            },
        ],
    )
    _write_jsonl(
        semantic_dir / "semantic_lift_edges.jsonl",
        [
            {
                "edge_id": "edge_steam_observed_by",
                "head_id": "stream:steam",
                "relation": "OBSERVED_BY",
                "tail_id": "variable:xmeas_19",
                "confidence": 0.82,
                "relation_family": "OBSERVATION",
            }
        ],
    )
    _write_jsonl(
        rca_dir / "nodes.jsonl",
        [
            {
                "node_id": "component:steam_valve",
                "entity_id": "component:steam_valve",
                "entity_type": "Component",
                "name": "Steam valve",
                "root_cause_candidate": True,
                "provenance_ids": ["ev_valve"],
            },
            {
                "node_id": "fault_anchor:fault_06",
                "entity_id": "fault_anchor:fault_06",
                "entity_type": "FaultAnchor",
                "name": "Fault 06 anchor",
                "provenance_ids": ["ev_fault"],
            },
        ],
    )
    _write_jsonl(
        rca_dir / "edges.jsonl",
        [
            {
                "edge_id": "rca_edge_steam_valve",
                "head_id": "component:steam_valve",
                "relation": "CAUSES",
                "tail_id": "fault_anchor:fault_06",
                "confidence": 0.74,
                "relation_family": "FAULT_SOURCE",
                "propagation_enabled": True,
                "provenance_ids": ["ev_rca_edge"],
            }
        ],
    )
    output_dir = tmp_path / "candidate"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_kg.py",
            "--tep-semantic-lift-dir",
            str(semantic_dir),
            "--tep-rca-graph-dir",
            str(rca_dir),
            "--output-dir",
            str(output_dir),
            "--run-id",
            "kgbuild_cli_tep_rca",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "source_to_kg_construction_result_v1" in completed.stdout
    assert (output_dir / "nodes.csv").exists()
    assert (output_dir / "edges.csv").exists()
    assert (output_dir / "draft_manifest.json").exists()
    assert (output_dir / "source_audit_graph_manifest.json").exists()
    assert (output_dir / "semantic_layer_manifest.json").exists()
    assert (output_dir / "rca_view_manifest.json").exists()
    assert (output_dir / "review_queue.json").exists()
    assert (output_dir / "publish_manifest.json").exists()
    assert (output_dir / "kg_construction_manifest.json").exists()
    summary = json.loads((output_dir / "kg_construction_summary.json").read_text())
    assert summary["kg_build_id"] == "kgbuild_cli_tep_rca"
    assert summary["source_ids"] == ["tep_semantic_lift", "tep_rca_graph"]
    assert summary["extractor_versions"] == {
        "tep_rca_graph": "v1",
        "tep_semantic_lift": "v1",
    }
    assert summary["profile_version"] == "tep_rca_v1"
    assert summary["review_policy"]
    assert summary["node_count"] == 4
    assert summary["edge_count"] == 2
    assert summary["output"]["manifest"].endswith("kg_construction_manifest.json")
    assert summary["output"]["publish_manifest"].endswith("publish_manifest.json")
    manifest = json.loads((output_dir / "kg_construction_manifest.json").read_text())
    assert manifest["summary"]["edge_count"] == 2
    assert set(_required_artifact_keys()) <= set(manifest["artifacts"])
    assert len(manifest["draft_rows"]) == 6


def test_build_source_kg_script_supports_toy_generic_structured_source(
    tmp_path: Path,
) -> None:
    """The CLI should expose a tiny generic source with complete version metadata."""
    output_dir = tmp_path / "toy_candidate"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_kg.py",
            "--toy-generic-structured-source",
            "--run-id",
            "kgbuild_cli_toy_generic",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "source_to_kg_construction_result_v1" in completed.stdout
    summary = json.loads((output_dir / "kg_construction_summary.json").read_text())
    manifest = json.loads((output_dir / "kg_construction_manifest.json").read_text())
    publish_manifest = json.loads((output_dir / "publish_manifest.json").read_text())

    assert summary["kg_build_id"] == "kgbuild_cli_toy_generic"
    assert summary["source_ids"] == ["toy_generic_source"]
    assert summary["extractor_versions"] == {"structured_record": "v1"}
    assert summary["profile_version"] == "generic_rca_v1"
    assert set(_required_artifact_keys()) <= set(summary["output"])
    assert set(_required_artifact_keys()) <= set(manifest["artifacts"])
    assert publish_manifest["kg_build_id"] == "kgbuild_cli_toy_generic"
    assert publish_manifest["source_ids"] == ["toy_generic_source"]


def test_build_source_kg_script_supports_offline_document_source(
    tmp_path: Path,
) -> None:
    """The CLI should build a document-source DraftKG without an LLM key."""
    output_dir = tmp_path / "toy_document_candidate"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_kg.py",
            "--toy-generic-document-source",
            "--run-id",
            "kgbuild_cli_toy_document",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "source_to_kg_construction_result_v1" in completed.stdout
    summary = json.loads((output_dir / "kg_construction_summary.json").read_text())
    audit_manifest = json.loads(
        (output_dir / "source_audit_graph_manifest.json").read_text()
    )
    review_queue = json.loads((output_dir / "review_queue.json").read_text())

    assert summary["kg_build_id"] == "kgbuild_cli_toy_document"
    assert summary["source_ids"] == ["toy_generic_document"]
    assert summary["extractor_versions"] == {"offline_document_ie": "v1"}
    assert summary["draft_entity_count"] == 4
    assert summary["draft_relation_count"] == 1
    assert summary["edge_count"] == 1
    parsed_source = audit_manifest["parsed_sources"][0]
    parsed_payload = json.dumps(parsed_source, sort_keys=True)
    assert parsed_source["kind"] == "text_chunks"
    assert parsed_source["chunk_count"] == 1
    assert "Cooling alert can suggest pump seal wear" not in parsed_payload
    assert review_queue[0]["relation_family"] == "CAUSES"
    assert review_queue[0]["review_status"] == "auto"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def _required_artifact_keys() -> set[str]:
    return {
        "nodes",
        "edges",
        "published_nodes",
        "published_edges",
        "draft_manifest",
        "source_audit_graph_manifest",
        "semantic_layer_manifest",
        "rca_view_manifest",
        "review_queue",
        "review_decisions",
        "publish_manifest",
        "publish_report",
        "summary",
        "manifest",
    }
