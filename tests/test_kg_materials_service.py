"""Tests for material-library service DTOs and handlers."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from kgtracevis.kg_construction.document_extraction import SourceTextChunk
from kgtracevis.service import kg_materials as service_kg_materials
from kgtracevis.service.kg_materials import (
    KGMaterialExtractionRunRequest,
    KGMaterialExtractionState,
    KGMaterialRecord,
    KGMaterialRegisterRequest,
    KGMaterialSelectedBuildRequest,
    configure_material_store_for_testing,
    extract_kg_material_to_structured_records,
    get_kg_material,
    list_kg_materials,
    prepare_kg_material_construction_build,
    register_kg_material,
    save_kg_material_upload,
)


def test_material_upload_persists_listable_record(tmp_path: Path) -> None:
    """Uploaded source materials should be stored without running extraction."""
    record = save_kg_material_upload(
        material_id="manual_pdf",
        title="Manual PDF",
        filename="manual.pdf",
        content=b"%PDF fixture",
        scenario="tep",
        material_type="pdf",
        content_type="application/pdf",
        material_root=tmp_path,
    )

    assert record.status == "uploaded"
    assert record.source_kind == "uploaded_file"
    assert record.extraction.status == "not_started"
    assert Path(record.source_uri).read_bytes() == b"%PDF fixture"
    assert Path(record.metadata_path).is_file()

    listing = list_kg_materials(material_root=tmp_path)
    assert [material.material_id for material in listing.materials] == ["manual_pdf"]

    detail = get_kg_material("manual_pdf", material_root=tmp_path)
    assert detail.material.title == "Manual PDF"
    assert detail.material.content_type == "application/pdf"


def test_material_register_stores_url_without_fetching(tmp_path: Path) -> None:
    """URL registration records provenance but does not create fetched content."""
    record = register_kg_material(
        KGMaterialRegisterRequest(
            material_id="paper_url",
            title="Reference paper",
            source_kind="url",
            source_uri="https://example.com/paper.pdf",
            material_type="webpage",
            metadata={"doi": "10.0000/example"},
        ),
        material_root=tmp_path,
    )

    assert record.status == "registered"
    assert record.source_uri == "https://example.com/paper.pdf"
    assert record.metadata["doi"] == "10.0000/example"
    assert not (tmp_path / "paper_url" / "paper.pdf").exists()


def test_material_extraction_writes_structured_records_with_fake_ie(
    tmp_path: Path,
) -> None:
    """Material extraction should update metadata and write build-ready JSONL."""
    source_path = tmp_path / "pump_note.txt"
    source_text = "Pump cavitation indicates seal wear."
    save_kg_material_upload(
        material_id="pump_note",
        title="Pump note",
        filename=source_path.name,
        content=source_text.encode(),
        scenario="tep",
        material_type="text",
        material_root=tmp_path,
    )

    response = extract_kg_material_to_structured_records(
        "pump_note",
        KGMaterialExtractionRunRequest(overwrite=True),
        client=FakeIEClient(),
        material_root=tmp_path,
    )

    assert response.status == "extracted"
    assert response.record_count == 3
    assert response.chunk_count == 1
    assert response.error_count == 0
    assert response.provider == "openai"
    assert response.extractor_name == "openai_document_ie"
    assert response.prompt_version == "document_ie_prompt_v1"
    assert response.material.extraction.status == "extracted"
    assert response.material.extraction.extractor_name == "openai_document_ie"
    assert response.material.extraction.extraction_manifest_path == (
        response.extraction_manifest_path
    )
    records_path = Path(response.structured_records_path)
    rows = [json.loads(line) for line in records_path.read_text().splitlines()]
    assert {row["record_type"] for row in rows} == {"entity", "relation"}
    assert rows[-1]["relation"] == "SUGGESTS_ROOT_CAUSE"
    chunk_results = [
        json.loads(line)
        for line in Path(response.chunk_results_path).read_text(encoding="utf-8").splitlines()
    ]
    assert chunk_results == [
        {
            "chunk_id": chunk_results[0]["chunk_id"],
            "chunk_index": 1,
            "entity_count": 2,
            "error_message": None,
            "relation_count": 1,
            "source_id": "pump_note",
            "status": "extracted",
        }
    ]
    manifest = json.loads(Path(response.extraction_manifest_path).read_text(encoding="utf-8"))
    assert manifest["claim_boundary"].startswith("Document IE output is source-grounded")
    assert manifest["extraction"]["provider"] == "openai"
    assert manifest["extraction"]["extractor_name"] == "openai_document_ie"
    assert manifest["extraction"]["prompt_version"] == "document_ie_prompt_v1"
    assert manifest["summary"]["review_status"] == "auto"
    assert manifest["summary"]["record_count"] == 3
    assert "Pump cavitation indicates seal wear." not in json.dumps(manifest)

    build_sources = prepare_kg_material_construction_build(
        KGMaterialSelectedBuildRequest(material_ids=["pump_note"]),
        material_root=tmp_path,
    )
    assert build_sources.sources[0].path == str(records_path)
    assert build_sources.sources[0].metadata["extraction_manifest_path"] == (
        response.extraction_manifest_path
    )


def test_material_extraction_supports_no_key_offline_fixture_provider(
    tmp_path: Path,
) -> None:
    """No-key extraction should replay source-grounded fixture candidates."""
    source_text = "Pump cavitation indicates seal wear."
    save_kg_material_upload(
        material_id="offline_note",
        title="Offline note",
        filename="offline_note.txt",
        content=source_text.encode(),
        scenario="tep",
        material_type="text",
        material_root=tmp_path,
    )

    response = extract_kg_material_to_structured_records(
        "offline_note",
        KGMaterialExtractionRunRequest(
            provider="offline_fixture",
            document_ie_payload=_offline_pump_fixture(),
            overwrite=True,
        ),
        material_root=tmp_path,
    )

    assert response.status == "extracted"
    assert response.provider == "offline_fixture"
    assert response.extractor_name == "offline_document_ie"
    assert response.record_count == 3
    assert response.material.extraction.extractor_name == "offline_document_ie"
    rows = [
        json.loads(line)
        for line in Path(response.structured_records_path).read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["relation"] == "SUGGESTS_ROOT_CAUSE"
    assert rows[-1]["metadata"]["prompt_version"] == "document_ie_prompt_v1"
    manifest = json.loads(Path(response.extraction_manifest_path).read_text(encoding="utf-8"))
    assert manifest["extraction"]["provider"] == "offline_fixture"
    assert manifest["extraction"]["extractor_name"] == "offline_document_ie"
    assert manifest["extraction"]["llm_boundary"].startswith("LLM extraction proposes")
    assert source_text not in json.dumps(manifest)


def test_material_extraction_long_context_writes_document_map(
    tmp_path: Path,
) -> None:
    """Document understanding mode should create advisory map artifacts."""
    source_text = (
        "# Pump Section\n"
        "Condition Monitoring (CM) observes Pump cavitation. "
        "Pump cavitation indicates seal wear."
    )
    save_kg_material_upload(
        material_id="mapped_note",
        title="Mapped note",
        filename="mapped_note.txt",
        content=source_text.encode(),
        scenario="tep",
        material_type="text",
        material_root=tmp_path,
    )
    client = PromptCapturingIEClient()

    response = extract_kg_material_to_structured_records(
        "mapped_note",
        KGMaterialExtractionRunRequest(
            document_understanding_mode="long_context",
            overwrite=True,
        ),
        client=client,
        material_root=tmp_path,
    )

    assert response.status == "extracted"
    assert response.document_understanding_map_path is not None
    assert response.material.extraction.document_understanding_mode == "long_context"
    assert response.material.extraction.document_understanding_map_path == (
        response.document_understanding_map_path
    )
    assert client.prompts
    assert "Document-level context for terminology only" in client.prompts[0]
    assert "current source text chunk" in client.prompts[0]

    document_map = json.loads(
        Path(response.document_understanding_map_path).read_text(encoding="utf-8")
    )
    assert document_map["mode"] == "long_context"
    assert document_map["artifact_type"] == "document_understanding_map_v1"
    assert document_map["cross_chunk_proposals"] == []
    assert document_map["glossary"][0]["term"] == "CM"
    assert document_map["sections"][0]["title"] == "Pump Section"
    assert "not DraftKG" in document_map["claim_boundary"]

    manifest = json.loads(Path(response.extraction_manifest_path).read_text(encoding="utf-8"))
    assert manifest["document_understanding"]["mode"] == "long_context"
    assert manifest["document_understanding"]["artifact_path"] == (
        response.document_understanding_map_path
    )
    build_sources = prepare_kg_material_construction_build(
        KGMaterialSelectedBuildRequest(material_ids=["mapped_note"]),
        material_root=tmp_path,
    )
    assert build_sources.sources[0].metadata["document_understanding_mode"] == "long_context"
    assert build_sources.sources[0].metadata["document_understanding_map_path"] == (
        response.document_understanding_map_path
    )


def test_offline_fixture_provider_requires_explicit_fixture(
    tmp_path: Path,
) -> None:
    """Offline provider must not silently fabricate candidates."""
    save_kg_material_upload(
        material_id="missing_fixture_note",
        title="Missing fixture note",
        filename="missing_fixture_note.txt",
        content=b"Pump cavitation indicates seal wear.",
        scenario="tep",
        material_type="text",
        material_root=tmp_path,
    )

    with pytest.raises(ValueError, match="provider=offline_fixture requires"):
        extract_kg_material_to_structured_records(
            "missing_fixture_note",
            KGMaterialExtractionRunRequest(provider="offline_fixture", overwrite=True),
            material_root=tmp_path,
        )


def test_material_extraction_writes_audit_artifacts_for_zero_candidates(
    tmp_path: Path,
) -> None:
    """A no-candidate IE result is still an auditable extraction outcome."""
    source_text = "This note has no supported KG candidates."
    save_kg_material_upload(
        material_id="empty_note",
        title="Empty note",
        filename="empty_note.txt",
        content=source_text.encode(),
        scenario="tep",
        material_type="text",
        material_root=tmp_path,
    )

    response = extract_kg_material_to_structured_records(
        "empty_note",
        KGMaterialExtractionRunRequest(overwrite=True),
        client=EmptyIEClient(),
        material_root=tmp_path,
    )

    assert response.status == "extracted"
    assert response.record_count == 0
    assert Path(response.structured_records_path).read_text(encoding="utf-8") == ""
    chunk_results = [
        json.loads(line)
        for line in Path(response.chunk_results_path).read_text(encoding="utf-8").splitlines()
    ]
    assert chunk_results[0]["status"] == "extracted"
    assert chunk_results[0]["entity_count"] == 0
    assert chunk_results[0]["relation_count"] == 0
    manifest = json.loads(Path(response.extraction_manifest_path).read_text(encoding="utf-8"))
    assert manifest["summary"]["record_count"] == 0
    assert manifest["summary"]["entity_count"] == 0
    assert manifest["summary"]["relation_count"] == 0
    assert source_text not in json.dumps(manifest)


def test_runtime_material_store_provider_persists_extraction_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured runtime stores should persist metadata while files stay on disk."""
    store = InMemoryMaterialStore()
    configure_material_store_for_testing(store)
    monkeypatch.setattr(service_kg_materials, "DEFAULT_SOURCE_KG_MATERIAL_DIR", tmp_path)
    try:
        record = save_kg_material_upload(
            material_id="runtime_note",
            title="Runtime note",
            filename="runtime_note.txt",
            content=b"Pump cavitation indicates seal wear.",
            scenario="tep",
            material_type="text",
        )

        response = extract_kg_material_to_structured_records(
            "runtime_note",
            KGMaterialExtractionRunRequest(overwrite=True),
            client=FakeIEClient(),
        )

        listing = list_kg_materials()
    finally:
        configure_material_store_for_testing(None)

    assert Path(record.source_uri).read_bytes() == b"Pump cavitation indicates seal wear."
    assert Path(response.structured_records_path).is_file()
    assert [material.material_id for material in listing.materials] == ["runtime_note"]
    assert store.records["runtime_note"].status == "extracted"
    assert store.records["runtime_note"].extraction.record_count == 3
    assert store.chunks["runtime_note"][0]["text_content"] == (
        "Pump cavitation indicates seal wear."
    )
    assert store.runs[0]["extraction"]["status"] == "extracted"
    assert store.runs[0]["provider"] == "openai"
    assert store.runs[0]["parameters"]["source_format"] == "jsonl"
    assert store.runs[0]["parameters"]["prompt_version"] == "document_ie_prompt_v1"
    assert store.runs[0]["result_summary"]["chunk_count"] == 1
    assert store.artifacts[0]["artifact_type"] == "structured_records"
    assert store.artifacts[0]["uri"] == response.structured_records_path
    assert [artifact["artifact_type"] for artifact in store.artifacts] == [
        "structured_records",
        "chunk_extraction_results",
        "extraction_manifest",
    ]


def test_selected_materials_prepare_build_ready_construction_sources(
    tmp_path: Path,
) -> None:
    """Extracted structured records should become source-to-KG build inputs."""
    records_path = tmp_path / "extracted_records.jsonl"
    records_path.write_text(
        json.dumps(
            {
                "id": "FeedTemperature",
                "name": "Feed temperature",
                "label": "Variable",
                "scenario": "tep",
                "evidence": "manual source row",
                "confidence": 0.7,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="tep_manual",
            title="TEP manual",
            source_kind="local_path",
            source_uri=str(tmp_path / "tep_manual.pdf"),
            scenario="tep",
            material_type="pdf",
            extraction=KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_format="jsonl",
                source_id="tep_manual_records",
                extractor_name="fake_extractor",
                extractor_version="v0",
                record_count=1,
            ),
        ),
        material_root=tmp_path,
    )

    response = prepare_kg_material_construction_build(
        KGMaterialSelectedBuildRequest(
            material_ids=["tep_manual"],
            output_name="selected_material_build",
            overwrite=True,
            run_id="kgbuild_material_unit",
        ),
        material_root=tmp_path,
    )

    assert response.status == "ready"
    assert response.construction_request.output_name == "selected_material_build"
    assert response.construction_request.overwrite is True
    assert response.construction_request.run_id == "kgbuild_material_unit"
    assert len(response.sources) == 1
    source = response.sources[0]
    assert source.source_id == "tep_manual_records"
    assert source.source_type == "structured_records"
    assert source.scenario == "tep"
    assert source.path == str(records_path)
    assert source.metadata["material_id"] == "tep_manual"
    assert source.metadata["extractor_name"] == "fake_extractor"


def test_selected_material_build_rejects_unextracted_material(tmp_path: Path) -> None:
    """Build preparation should fail with a concrete 4xx-friendly message."""
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="unparsed_manual",
            title="Unparsed manual",
            source_kind="url",
            source_uri="https://example.com/manual.pdf",
            material_type="pdf",
        ),
        material_root=tmp_path,
    )

    with pytest.raises(ValueError, match="extraction.status must be extracted"):
        prepare_kg_material_construction_build(
            KGMaterialSelectedBuildRequest(material_ids=["unparsed_manual"]),
            material_root=tmp_path,
        )


def test_selected_material_build_rejects_missing_structured_records(
    tmp_path: Path,
) -> None:
    """Extracted metadata must point at an existing local records file."""
    missing_path = tmp_path / "missing.jsonl"
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="missing_records",
            title="Missing records",
            source_kind="local_path",
            source_uri=str(tmp_path / "source.pdf"),
            extraction=KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(missing_path),
            ),
        ),
        material_root=tmp_path,
    )

    with pytest.raises(ValueError, match="structured records not found"):
        prepare_kg_material_construction_build(
            KGMaterialSelectedBuildRequest(material_ids=["missing_records"]),
            material_root=tmp_path,
        )


def test_material_dtos_reject_unsafe_or_ambiguous_inputs() -> None:
    """DTO validation should produce deterministic service-boundary errors."""
    with pytest.raises(ValidationError, match="material_id must be a single path component"):
        KGMaterialSelectedBuildRequest(material_ids=["../bad"])

    with pytest.raises(ValidationError, match="source_kind=url requires source_uri"):
        KGMaterialRegisterRequest(
            material_id="bad_url",
            title="Bad URL",
            source_kind="url",
            source_uri="/local/path.pdf",
        )

    with pytest.raises(ValidationError, match="material_ids contains duplicates"):
        KGMaterialSelectedBuildRequest(material_ids=["same", "same"])

    with pytest.raises(ValidationError, match="source_format must be jsonl"):
        KGMaterialExtractionRunRequest(source_format="csv")

    with pytest.raises(ValidationError, match="require provider=offline_fixture"):
        KGMaterialExtractionRunRequest(document_ie_payload={})


class FakeIEClient:
    """Fake document IE client for material extraction service tests."""

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


class EmptyIEClient:
    """Fake document IE client that returns no candidates."""

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del chunk, prompt, response_schema
        return {"entities": [], "relations": []}


class PromptCapturingIEClient(FakeIEClient):
    """Fake IE client that records prompts for context-boundary assertions."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        return super().extract_candidates(
            chunk,
            prompt=prompt,
            response_schema=response_schema,
        )


def _offline_pump_fixture() -> dict[str, Any]:
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
                "evidence": "Pump cavitation indicates seal wear.",
                "confidence": 0.55,
            }
        ],
    }


class InMemoryMaterialStore:
    """Small material-store fake for runtime provider tests."""

    def __init__(self) -> None:
        self.records: dict[str, KGMaterialRecord] = {}
        self.chunks: dict[str, list[dict[str, Any]]] = {}
        self.runs: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []

    def save_material_record(self, material: KGMaterialRecord) -> KGMaterialRecord:
        self.records[material.material_id] = material
        return material

    def list_material_records(self) -> list[KGMaterialRecord]:
        return list(self.records.values())

    def get_material_record(self, material_id: str) -> KGMaterialRecord:
        try:
            return self.records[material_id]
        except KeyError as exc:
            raise ValueError(f"unknown material_id: {material_id}") from exc

    def save_source_chunks(
        self,
        material_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.chunks[material_id] = chunks
        return chunks

    def record_extraction_run(
        self,
        material_id: str,
        extraction: KGMaterialExtractionState,
        *,
        extraction_run_id: str | uuid.UUID | None = None,
        provider: str | None = None,
        parameters: dict[str, Any] | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = {
            "extraction_run_id": str(extraction_run_id or "runtime-extraction-001"),
            "material_id": material_id,
            "status": extraction.status,
            "provider": provider,
            "extraction": extraction.model_dump(mode="json"),
            "parameters": parameters or {},
            "result_summary": result_summary or {},
        }
        self.runs.append(run)
        return run

    def save_extraction_artifact(
        self,
        *,
        material_id: str,
        artifact_type: str,
        extraction_run_id: str | uuid.UUID | None = None,
        uri: str | None = None,
        media_type: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact = {
            "artifact_id": "runtime-artifact-001",
            "material_id": material_id,
            "extraction_run_id": str(extraction_run_id) if extraction_run_id else None,
            "artifact_type": artifact_type,
            "uri": uri,
            "media_type": media_type,
            "payload": payload or {},
        }
        self.artifacts.append(artifact)
        return artifact
