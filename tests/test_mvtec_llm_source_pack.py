"""Tests for raw-material MVTec LLM KG construction smoke workflows."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.workflows.mvtec_llm_source_pack import (
    EXCLUDED_DERIVED_SOURCE_NAMES,
    MVTecLLMSourcePackConfig,
    build_mvtec_llm_source_pack,
)


def test_mvtec_llm_source_pack_uses_raw_materials_and_excludes_derived_kg(
    tmp_path: Path,
) -> None:
    """Source pack should include prose/source snapshots, not generated KG tables."""
    source_bundle = tmp_path / "source_bundle"
    defect_spectrum = tmp_path / "Defect_Spectrum"
    source_bundle.mkdir()
    (defect_spectrum / "DS-MVTec").mkdir(parents=True)
    (source_bundle / "mvtec_ad_official_page.html").write_text(
        "<html><body>MVTec AD has industrial anomaly detection data.</body></html>",
        encoding="utf-8",
    )
    (source_bundle / "README.md").write_text("MVTec source bundle notes.", encoding="utf-8")
    (source_bundle / "patchcore_arxiv_abs.html").write_text(
        "<html><body>PatchCore detects anomalies.</body></html>",
        encoding="utf-8",
    )
    (defect_spectrum / "DS-MVTec" / "DS-MVTec.md").write_text(
        "# DS-MVTec\n\n## defect classes\nbottle broken_large",
        encoding="utf-8",
    )
    for excluded in EXCLUDED_DERIVED_SOURCE_NAMES[:3]:
        (defect_spectrum / excluded).write_text("derived", encoding="utf-8")

    result = build_mvtec_llm_source_pack(
        MVTecLLMSourcePackConfig(
            output_dir=tmp_path / "pack",
            mvtec_source_bundle_dir=source_bundle,
            defect_spectrum_dir=defect_spectrum,
        )
    )

    material_ids = {item["material_id"] for item in result.manifest["materials"]}
    copied_names = {path.name for path in result.copied_source_dir.iterdir()}

    assert material_ids == {
        "ds_mvtec_dataset_card",
        "flow_mark_defect_web_reference",
        "injection_molding_defects_web_table",
        "molding_flash_defect_web_reference",
        "mvtec_ad_official_page",
        "mvtec_source_bundle_readme",
        "patchcore_arxiv_abs",
    }
    assert not copied_names.intersection(EXCLUDED_DERIVED_SOURCE_NAMES)
    assert result.manifest["source_policy"]["excluded"].startswith("prebuilt KG")


def test_mvtec_llm_source_pack_includes_optional_pdf_rca_sources(
    tmp_path: Path,
) -> None:
    """Optional paper/process PDFs should enter the pack when locally available."""
    source_bundle = tmp_path / "source_bundle"
    defect_spectrum = tmp_path / "Defect_Spectrum"
    raw_dir = source_bundle / "raw"
    raw_dir.mkdir(parents=True)
    (defect_spectrum / "DS-MVTec").mkdir(parents=True)
    (source_bundle / "mvtec_ad_official_page.html").write_text(
        "<html><body>MVTec AD has industrial anomaly detection data.</body></html>",
        encoding="utf-8",
    )
    (source_bundle / "README.md").write_text("MVTec source bundle notes.", encoding="utf-8")
    (defect_spectrum / "DS-MVTec" / "DS-MVTec.md").write_text(
        "# DS-MVTec\n\n## defect classes\nbottle broken_large",
        encoding="utf-8",
    )
    (source_bundle / "visual_defect_survey_mdpi.html").write_text(
        "<html><body>scratches, shape error, crack, bump defects</body></html>",
        encoding="utf-8",
    )
    (raw_dir / "mvtec_ad_cvpr_2019.pdf").write_bytes(b"%PDF-1.3\nfixture")
    (raw_dir / "injection_molding_root_causes.pdf").write_bytes(b"%PDF-1.7\nfixture")
    (raw_dir / "plastic_injection_molding_defects_chart.pdf").write_bytes(
        b"%PDF-1.6\nfixture"
    )

    result = build_mvtec_llm_source_pack(
        MVTecLLMSourcePackConfig(
            output_dir=tmp_path / "pack",
            mvtec_source_bundle_dir=source_bundle,
            defect_spectrum_dir=defect_spectrum,
            include_patchcore=False,
        )
    )

    by_id = {item["material_id"]: item for item in result.manifest["materials"]}

    assert by_id["mvtec_ad_paper_pdf"]["material_type"] == "pdf"
    assert by_id["injection_molding_root_causes_pdf"]["metadata"][
        "source_pack_role"
    ] == "manufacturing_process_root_cause_context"
    assert by_id["injection_molding_defects_chart_pdf"]["material_type"] == "pdf"
    assert by_id["visual_defect_survey_html"]["material_type"] == "webpage"


def test_mvtec_llm_source_pack_includes_remote_root_cause_references(
    tmp_path: Path,
) -> None:
    """Remote raw references can enter the pack without prebuilt KG artifacts."""
    source_bundle = tmp_path / "source_bundle"
    defect_spectrum = tmp_path / "Defect_Spectrum"
    source_bundle.mkdir(parents=True)
    (defect_spectrum / "DS-MVTec").mkdir(parents=True)
    (source_bundle / "mvtec_ad_official_page.html").write_text(
        "<html><body>MVTec AD has industrial anomaly detection data.</body></html>",
        encoding="utf-8",
    )
    (defect_spectrum / "DS-MVTec" / "DS-MVTec.md").write_text(
        "# DS-MVTec\n\n## defect classes\nbottle broken_large",
        encoding="utf-8",
    )

    result = build_mvtec_llm_source_pack(
        MVTecLLMSourcePackConfig(
            output_dir=tmp_path / "pack",
            mvtec_source_bundle_dir=source_bundle,
            defect_spectrum_dir=defect_spectrum,
            include_patchcore=False,
        )
    )

    by_id = {item["material_id"]: item for item in result.manifest["materials"]}

    assert by_id["injection_molding_defects_web_table"]["source_kind"] == "url"
    assert by_id["flow_mark_defect_web_reference"]["scenario"] == "mvtec"
    assert by_id["molding_flash_defect_web_reference"]["metadata"][
        "source_pack_role"
    ] == "manufacturing_process_root_cause_context"
