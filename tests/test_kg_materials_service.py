"""Tests for source material management with the source KG compiler path."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.service.kg_materials import (
    KGMaterialRegisterRequest,
    extract_kg_material_to_structured_records,
    list_kg_materials,
    prepare_kg_material_construction_build,
    register_kg_material,
    save_kg_material_upload,
)


def test_material_upload_registers_compiler_ready_source(tmp_path: Path) -> None:
    """Uploaded materials should become selectable compiler source inputs."""
    record = save_kg_material_upload(
        material_id="material_001",
        title="Manual notes",
        filename="notes.txt",
        content=b"SCENARIO: mvtec\nScratch defects have linear evidence.",
        scenario="mvtec",
        material_type="text",
        material_root=tmp_path,
    )

    assert record.is_build_ready
    listing = list_kg_materials(material_root=tmp_path)
    assert [item.material_id for item in listing.materials] == ["material_001"]

    prepared = prepare_kg_material_construction_build(
        request=_selection(["material_001"]),
        material_root=tmp_path,
    )
    assert prepared.sources[0].path == record.source_uri
    assert prepared.construction_request.sources[0].scenario == "mvtec"


def test_material_extraction_marks_local_path_compiler_ready(tmp_path: Path) -> None:
    """Local-path materials can be marked ready without legacy DraftKG extraction."""
    source = tmp_path / "source.md"
    source.write_text("SCENARIO: wafer\nCenter pattern notes.", encoding="utf-8")
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="local_001",
            title="Local source",
            source_kind="local_path",
            source_uri=source.as_posix(),
            scenario="wafer",
            material_type="markdown",
        ),
        material_root=tmp_path,
    )

    result = extract_kg_material_to_structured_records(
        "local_001",
        request=_extract_request(),
        material_root=tmp_path,
    )

    assert result.structured_records_path == source.as_posix()
    assert result.material.extraction.status == "extracted"
    assert Path(result.extraction_manifest_path).is_file()


def _selection(material_ids: list[str]):
    from kgtracevis.service.kg_materials import KGMaterialSelectedBuildRequest

    return KGMaterialSelectedBuildRequest(material_ids=material_ids, output_name="unit")


def _extract_request():
    from kgtracevis.service.kg_materials import KGMaterialExtractionRunRequest

    return KGMaterialExtractionRunRequest(overwrite=True)
