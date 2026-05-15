"""Tests for material-library driven KG construction workflow orchestration."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from kgtracevis.kg_construction.document_extraction import SourceTextChunk
from kgtracevis.service.kg_materials import (
    KGMaterialExtractionRunRequest,
    KGMaterialExtractionState,
    KGMaterialRegisterRequest,
    register_kg_material,
    save_kg_material_upload,
)
from kgtracevis.workflows.material_kg_construction import (
    MaterialKGConstructionWorkflowConfig,
    run_material_kg_construction_workflow,
)


def test_material_workflow_extracts_selected_material_and_builds_artifacts(
    tmp_path: Path,
) -> None:
    """Selected materials can be extracted with a fake IE client and built."""
    material_root = tmp_path / "materials"
    output_dir = tmp_path / "material_build"
    save_kg_material_upload(
        material_id="pump_note",
        title="Pump note",
        filename="pump_note.txt",
        content=b"Pump cavitation indicates seal wear.",
        scenario="tep",
        material_type="text",
        material_root=material_root,
    )

    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=("pump_note",),
            material_root=material_root,
            output_dir=output_dir,
            run_id="kgbuild_material_unit",
            extraction_mode="missing",
            extraction_request=KGMaterialExtractionRunRequest(overwrite=True),
        ),
        client=FakeIEClient(),
    )

    assert result.run_id == "kgbuild_material_unit"
    assert result.nodes_path == output_dir / "nodes.csv"
    assert result.edges_path == output_dir / "edges.csv"
    assert len(result.extraction_results) == 1
    assert result.materials[0].is_build_ready is True
    assert result.sources[0].source_id == "pump_note"
    assert result.summary["material_library"] == {
        "material_root": str(material_root),
        "material_count": 1,
        "material_ids": ["pump_note"],
        "source_ids": ["pump_note"],
        "extraction_mode": "missing",
        "extracted_material_ids": ["pump_note"],
        "claim_boundary": (
            "material-derived KG rows are source-grounded candidates for review; "
            "selection or extraction does not verify industrial facts or publish to Neo4j"
        ),
    }
    persisted_summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert persisted_summary["material_library"]["material_ids"] == ["pump_note"]

    edge_rows = _read_csv_rows(result.edges_path)
    assert edge_rows[0]["head"] == "PumpCavitation"
    assert edge_rows[0]["tail"] == "SealWear"
    assert edge_rows[0]["source"] == "pump_note"
    assert edge_rows[0]["review_status"] == "auto"
    assert (
        "does not verify industrial facts"
        in result.summary["material_library"]["claim_boundary"]
    )


def test_material_workflow_builds_pre_extracted_material_without_ie_client(
    tmp_path: Path,
) -> None:
    """Pre-extracted material records should build without live extraction."""
    material_root = tmp_path / "materials"
    output_dir = tmp_path / "material_build"
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "FeedTemperature",
                        "name": "Feed temperature",
                        "label": "Variable",
                        "scenario": "tep",
                        "source": "tep_manual_records",
                        "evidence": "source row",
                        "confidence": 0.72,
                    }
                ),
                json.dumps(
                    {
                        "id": "ReactorUnit",
                        "name": "Reactor unit",
                        "label": "ProcessUnit",
                        "scenario": "tep",
                        "source": "tep_manual_records",
                        "evidence": "source row",
                        "confidence": 0.72,
                    }
                ),
                json.dumps(
                    {
                        "head": "FeedTemperature",
                        "relation": "BELONGS_TO",
                        "tail": "ReactorUnit",
                        "scenario": "tep",
                        "source": "tep_manual_records",
                        "evidence": "candidate relation from source row",
                        "confidence": 0.72,
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="tep_manual",
            title="TEP manual",
            source_kind="local_path",
            source_uri=str(tmp_path / "manual.txt"),
            scenario="tep",
            material_type="text",
            extraction=KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_id="tep_manual_records",
                record_count=3,
            ),
        ),
        material_root=material_root,
    )

    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=("tep_manual",),
            material_root=material_root,
            output_dir=output_dir,
            extraction_mode="never",
        )
    )

    assert result.extraction_results == ()
    assert result.summary["node_count"] == 2
    assert result.summary["edge_count"] == 1
    assert result.summary["material_library"]["extraction_mode"] == "never"
    assert _read_csv_rows(result.edges_path)[0]["source"] == "tep_manual_records"


def test_material_workflow_rejects_unextracted_material_without_extraction(
    tmp_path: Path,
) -> None:
    """The workflow should not silently build unextracted materials."""
    material_root = tmp_path / "materials"
    save_kg_material_upload(
        material_id="raw_note",
        title="Raw note",
        filename="raw_note.txt",
        content=b"Raw source text.",
        material_type="text",
        material_root=material_root,
    )

    with pytest.raises(ValueError, match="extraction.status must be extracted"):
        run_material_kg_construction_workflow(
            MaterialKGConstructionWorkflowConfig(
                material_ids=("raw_note",),
                material_root=material_root,
                output_dir=tmp_path / "material_build",
                extraction_mode="never",
            )
        )


class FakeIEClient:
    """Fake document IE client for workflow tests."""

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del prompt, response_schema
        return {
            "entities": [
                {
                    "id": "PumpCavitation",
                    "name": "Pump cavitation",
                    "label": "FaultEvent",
                    "evidence": "Pump cavitation",
                },
                {
                    "id": "SealWear",
                    "name": "Seal wear",
                    "label": "RootCause",
                    "evidence": "seal wear",
                },
            ],
            "relations": [
                {
                    "head": "PumpCavitation",
                    "relation": "SUGGESTS_ROOT_CAUSE",
                    "tail": "SealWear",
                    "evidence": chunk.text,
                    "confidence": 0.55,
                }
            ],
        }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
