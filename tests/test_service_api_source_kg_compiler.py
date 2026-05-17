"""Focused API tests for source_kg_compiler-aligned build features."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient

from kgtracevis.service import kg_construction as service_kg_construction
from kgtracevis.service import kg_materials as service_kg_materials
from kgtracevis.service.api import app
from kgtracevis.service.kg_materials import KGMaterialExtractionState, KGMaterialRegisterRequest


class FakeCompilerLLM:
    """Deterministic fake for document-source compiler API tests."""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        if "knowledge cards" in system_prompt:
            return json.dumps(
                {
                    "cards": [
                        {
                            "card_id": "doc_card_001",
                            "scenario": "mvtec",
                            "claim": "ScratchDefect HAS_PLAUSIBLE_CAUSE MechanicalContact",
                            "entities_mentioned": ["ScratchDefect", "MechanicalContact"],
                            "relation_hints": [
                                "ScratchDefect HAS_PLAUSIBLE_CAUSE MechanicalContact"
                            ],
                            "source_chunk_id": "ignored",
                            "source_material_ids": ["doc_manual"],
                            "evidence_text": "Scratch may indicate mechanical contact.",
                        }
                    ]
                }
            )
        if "canonical entities" in system_prompt:
            return json.dumps(
                {
                    "entities": [
                        {
                            "entity_id": "ScratchDefect",
                            "canonical_name": "ScratchDefect",
                            "entity_type": "Defect",
                            "aliases": ["scratch"],
                            "description": "Scratch defect.",
                            "scenario": "mvtec",
                            "source_card_ids": ["doc_card_001"],
                        },
                        {
                            "entity_id": "MechanicalContact",
                            "canonical_name": "MechanicalContact",
                            "entity_type": "CandidateCause",
                            "aliases": [],
                            "description": "Mechanical contact cause.",
                            "scenario": "mvtec",
                            "source_card_ids": ["doc_card_001"],
                        },
                    ]
                }
            )
        if "construct edges" in system_prompt:
            return json.dumps(
                {
                    "edges": [
                        {
                            "edge_id": "doc_edge_001",
                            "source": "ScratchDefect",
                            "relation": "HAS_PLAUSIBLE_CAUSE",
                            "target": "MechanicalContact",
                            "scenario": "mvtec",
                            "evidence": "Scratch may indicate mechanical contact.",
                            "source_card_ids": ["doc_card_001"],
                            "confidence": 0.81,
                            "review_status": "auto",
                        }
                    ]
                }
            )
        if "reasoning profiles" in system_prompt:
            return json.dumps({"profiles": {"mvtec": {}}})
        raise AssertionError(system_prompt)

    def repair_json(self, broken_json: str, error: str) -> str:
        return broken_json


def test_document_construction_build_uses_compiler_branch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Document/text sources should route through source_kg_compiler artifacts."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    monkeypatch.setattr(
        service_kg_construction,
        "OpenAICompatibleSourceKGLLM",
        lambda: FakeCompilerLLM(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "document_runtime",
            "overwrite": True,
            "run_id": "kgbuild_document_unit",
            "llm_concurrency": 2,
            "sources": [
                {
                    "source_id": "doc_manual",
                    "source_type": "document",
                    "scenario": "mvtec",
                    "source_format": "markdown",
                    "source_text": "# Scratch note\n\nScratch may indicate mechanical contact.",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "kgbuild_document_unit"
    assert payload["summary"]["node_count"] == 2
    assert payload["summary"]["edge_count"] == 1
    assert payload["source_units_path"].endswith("source_units.jsonl")
    assert payload["knowledge_cards_path"].endswith("knowledge_cards.jsonl")
    assert payload["validation_report_path"].endswith("validation_report.json")
    assert Path(payload["nodes_path"]).is_file()
    assert Path(payload["edges_path"]).is_file()
    assert Path(payload["manifest_path"]).is_file()

    detail = client.get("/api/kg/construction/builds/kgbuild_document_unit")
    assert detail.status_code == 200
    assert detail.json()["manifest"]["run"]["metadata"]["builder"] == "source_kg_compiler"

    artifact = client.get(
        "/api/kg/construction/builds/kgbuild_document_unit/artifacts/source_units"
    )
    assert artifact.status_code == 200
    assert "doc_manual" in artifact.text


def test_validate_overlay_route_and_artifact_download(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Overlay validation and artifact download should work on registered builds."""
    build_root = tmp_path / "source_kg_build"
    monkeypatch.setattr(service_kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", build_root)
    build_dir = build_root / "overlay_runtime"
    build_dir.mkdir(parents=True)
    _write_csv(
        build_dir / "nodes.csv",
        [
            {
                "id": "OverlayCoolingAlert",
                "name": "Overlay cooling alert",
                "label": "FaultType",
                "scenario": "shared",
                "aliases": "overlay cooling alert",
                "description": "Runtime overlay source node",
            },
            {
                "id": "OverlaySealWear",
                "name": "Overlay seal wear",
                "label": "RootCause",
                "scenario": "shared",
                "aliases": "overlay seal wear",
                "description": "Runtime overlay RCA target",
            },
        ],
    )
    _write_csv(
        build_dir / "edges.csv",
        [
            {
                "head": "OverlayCoolingAlert",
                "relation": "CAUSES",
                "tail": "OverlaySealWear",
                "scenario": "shared",
                "source": "overlay_validation_fixture",
                "evidence": "Fixture row links overlay cooling alert to seal wear.",
                "confidence": "0.82",
                "weight": "0.18",
                "review_status": "auto",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
                "relation_family": "CAUSES",
                "propagation_enabled": "true",
                "propagation_direction": "forward",
                "propagation_priority": "1.0",
                "attenuation": "0.9",
                "edge_weight": "0.23",
                "root_candidate": "true",
                "observable": "false",
                "event_anchor": "OverlayCoolingAlert",
                "fault_anchor": "OverlaySealWear",
                "task_view": "overlay_validation",
                "confidence_policy": "min",
                "source_trust": "0.8",
                "rca_score": "0.77",
                "rca_score_confidence": "0.82",
                "rca_score_priority": "1.0",
                "rca_score_attenuation": "0.9",
                "rca_score_source_trust": "0.8",
                "external_edge_id": "fixture_edge_001",
                "kg_build_id": "kgbuild_overlay_api",
            }
        ],
    )
    summary = {
        "artifact_type": "source_to_kg_construction_result_v1",
        "run_id": "kgbuild_overlay_api",
        "source_count": 1,
        "source_ids": ["overlay_fixture"],
        "draft_entity_count": 0,
        "draft_relation_count": 0,
        "node_count": 2,
        "edge_count": 1,
        "node_labels": {},
        "edge_relations": {"CAUSES": 1},
        "scenarios": {"shared": 1},
        "review_status_counts": {"auto": 1},
    }
    (build_dir / "kg_construction_summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    manifest = {
        "artifact_type": "source_to_kg_construction_manifest_v1",
        "run": {
            "run_id": "kgbuild_overlay_api",
            "created_at": "2026-05-17T00:00:00+00:00",
            "status": "built",
            "source_ids": ["overlay_fixture"],
            "scenario_counts": {"shared": 1},
        },
        "summary": summary,
        "sources": [],
        "artifacts": {
            "output_dir": build_dir.as_posix(),
            "nodes": (build_dir / "nodes.csv").as_posix(),
            "edges": (build_dir / "edges.csv").as_posix(),
            "summary": (build_dir / "kg_construction_summary.json").as_posix(),
            "manifest": (build_dir / "kg_construction_manifest.json").as_posix(),
        },
        "draft_rows": [],
        "review_decisions": [],
    }
    (build_dir / "kg_construction_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    example_dir = tmp_path / "examples"
    example_dir.mkdir()
    (example_dir / "overlay_case.json").write_text(
        json.dumps(
            {
                "case_id": "overlay_case_001",
                "dataset": "mvtec",
                "source": "unknown",
                "object": "pump",
                "anomaly_type": "Overlay cooling alert",
                "location": None,
                "morphology": None,
                "severity": 0.7,
                "confidence": 0.8,
                "timestamp": None,
                "raw_evidence": {
                    "variables": [],
                    "variable_contributions": {},
                    "log_events": [],
                    "description": "Overlay validation fixture.",
                },
                "normalized_evidence": {},
                "kg_analysis": {},
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/kg/construction/builds/kgbuild_overlay_api/validate-overlay",
        json={"example_dir": str(example_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["build"]["run_id"] == "kgbuild_overlay_api"
    assert payload["report"]["validated"] is True
    assert payload["report"]["overlay_contributed"] is True
    assert payload["report"]["overlay_contribution_kg_build_ids"] == ["kgbuild_overlay_api"]

    artifact = client.get(
        "/api/kg/construction/builds/kgbuild_overlay_api/artifacts/kg_overlay_validation_report"
    )
    assert artifact.status_code == 200
    assert "overlay_contributed" in artifact.text


def test_materials_build_route_uses_existing_build_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Direct material builds should reuse current extracted structured-record sources."""
    material_root = tmp_path / "materials"
    build_root = tmp_path / "source_kg_build"
    monkeypatch.setattr(service_kg_materials, "DEFAULT_SOURCE_KG_MATERIAL_DIR", material_root)
    monkeypatch.setattr(service_kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", build_root)

    records_path = material_root / "prebuilt" / "structured_records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "MaterialSource",
                        "name": "Material source",
                        "label": "Variable",
                        "scenario": "tep",
                        "evidence": "source row",
                        "confidence": 0.71,
                    }
                ),
                json.dumps(
                    {
                        "id": "MaterialTarget",
                        "name": "Material target",
                        "label": "ProcessUnit",
                        "scenario": "tep",
                        "evidence": "target row",
                        "confidence": 0.71,
                    }
                ),
                json.dumps(
                    {
                        "head": "MaterialSource",
                        "relation": "BELONGS_TO",
                        "tail": "MaterialTarget",
                        "scenario": "tep",
                        "evidence": "relation row",
                        "confidence": 0.71,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    service_kg_materials.register_kg_material(
        KGMaterialRegisterRequest(
            material_id="prebuilt_material",
            title="Prebuilt material",
            source_kind="local_path",
            source_uri=str(material_root / "prebuilt" / "note.txt"),
            scenario="tep",
            material_type="text",
            extraction=KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_format="jsonl",
                source_id="prebuilt_material",
                extractor_name="fixture",
                extractor_version="v1",
                record_count=3,
            ),
        ),
        material_root=material_root,
    )

    client = TestClient(app)
    response = client.post(
        "/api/kg/materials/build",
        json={
            "material_ids": ["prebuilt_material"],
            "output_name": "material_direct_build",
            "overwrite": True,
            "source_type": "structured_records",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["material_ids"] == ["prebuilt_material"]
    assert payload["source_ids"] == ["prebuilt_material"]
    assert Path(payload["nodes_path"]).is_file()
    assert Path(payload["edges_path"]).is_file()
    edge_rows = _read_csv_rows(Path(payload["edges_path"]))
    assert edge_rows[0]["head"] == "MaterialSource"
    assert edge_rows[0]["tail"] == "MaterialTarget"


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
