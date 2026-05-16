"""Tests for wafer/WM811K raw-material LLM source packs."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.workflows.wafer_llm_source_pack import (
    WaferLLMSourcePackConfig,
    build_wafer_llm_source_pack,
)


def test_wafer_llm_source_pack_includes_remote_papers_and_records(
    tmp_path: Path,
) -> None:
    """Wafer source packs should combine public pages and local WM811K records."""
    records = tmp_path / "wm811k_records.jsonl"
    records.write_text('{"dataset":"wafer","failure_pattern":"Center"}\n', encoding="utf-8")

    result = build_wafer_llm_source_pack(
        WaferLLMSourcePackConfig(
            output_dir=tmp_path / "pack",
            wm811k_records_path=records,
        )
    )

    by_id = {item["material_id"]: item for item in result.manifest["materials"]}
    material_ids = [item["material_id"] for item in result.manifest["materials"]]

    assert by_id["wafer_map_scientific_reports_2023"]["source_kind"] == "url"
    assert by_id["wafer_defect_frontiers_2023"]["scenario"] == "wafer"
    assert by_id["wm811k_example_records"]["source_kind"] == "local_path"
    assert Path(by_id["wm811k_example_records"]["source_uri"]).is_file()
    assert material_ids[:2] == ["wafer_defect_frontiers_2023", "wm811k_example_records"]


def test_wafer_llm_source_pack_can_skip_missing_records(tmp_path: Path) -> None:
    """Missing optional WM811K records should be audited, not fatal."""
    result = build_wafer_llm_source_pack(
        WaferLLMSourcePackConfig(
            output_dir=tmp_path / "pack",
            wm811k_records_path=tmp_path / "missing.jsonl",
        )
    )

    material_ids = {item["material_id"] for item in result.manifest["materials"]}

    assert "wm811k_example_records" not in material_ids
    assert result.manifest["skipped"] == [
        {
            "material_id": "wm811k_example_records",
            "path": str(tmp_path / "missing.jsonl"),
            "reason": "missing",
        }
    ]
