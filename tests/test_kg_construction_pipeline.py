"""Tests for the reusable source-to-KG construction pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kgtracevis.kg_construction import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    ExtractorRegistry,
    KGConstructionSource,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    draft_status_to_review_status,
    run_kg_construction,
    tep_external_id_to_kg_id,
)


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


def test_build_source_kg_script_writes_candidate_artifacts(tmp_path: Path) -> None:
    """The source-to-KG CLI should write candidate CSV and summary artifacts."""
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
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
    output_dir = tmp_path / "candidate"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_kg.py",
            "--tep-semantic-lift-dir",
            str(semantic_dir),
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "source_to_kg_construction_result_v1" in completed.stdout
    assert (output_dir / "nodes.csv").exists()
    assert (output_dir / "edges.csv").exists()
    assert (output_dir / "kg_construction_manifest.json").exists()
    summary = json.loads((output_dir / "kg_construction_summary.json").read_text())
    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["output"]["manifest"].endswith("kg_construction_manifest.json")
    manifest = json.loads((output_dir / "kg_construction_manifest.json").read_text())
    assert manifest["summary"]["edge_count"] == 1
    assert len(manifest["draft_rows"]) == 3


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
