"""Tests for raw-material MVTec LLM KG construction smoke workflows."""

from __future__ import annotations

import json
import subprocess
import sys
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
        "mvtec_ad_official_page",
        "mvtec_source_bundle_readme",
        "patchcore_arxiv_abs",
    }
    assert not copied_names.intersection(EXCLUDED_DERIVED_SOURCE_NAMES)
    assert result.manifest["source_policy"]["excluded"].startswith("prebuilt KG")


def test_smoke_mvtec_llm_kg_construction_cli_runs_offline_fixture(
    tmp_path: Path,
) -> None:
    """Smoke CLI should run raw materials through DU, IE, brainstorming, and review."""
    pack = _write_tiny_source_pack(tmp_path)
    output_dir = tmp_path / "smoke"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_mvtec_llm_kg_construction.py",
            "--source-pack",
            str(pack),
            "--output-dir",
            str(output_dir),
            "--provider",
            "offline_fixture",
            "--overwrite",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["artifact_type"] == "mvtec_llm_kg_construction_smoke_result_v1"
    assert payload["profile_version"] == "mvtec_rca_v1"
    assert payload["edge_count"] >= 1
    assert payload["published_edge_count"] == 0
    assert "hypothesis_candidate" in payload["review_item_types"]
    assert Path(payload["artifacts"]["document_map"]).is_file()
    assert Path(payload["artifacts"]["brainstorm_hypotheses"]).is_file()


def _write_tiny_source_pack(tmp_path: Path) -> Path:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    official = source_dir / "mvtec_ad_official_page.html"
    official.write_text(
        "<html><body>MVTec AD is an industrial anomaly detection benchmark.</body></html>",
        encoding="utf-8",
    )
    dataset_card = source_dir / "ds_mvtec_dataset_card.md"
    dataset_card.write_text(
        "# DS-MVTec\n\n## defect classes\nbottle broken_large",
        encoding="utf-8",
    )
    pack = tmp_path / "mvtec_llm_source_pack.json"
    pack.write_text(
        json.dumps(
            {
                "artifact_type": "mvtec_llm_source_pack_v1",
                "materials": [
                    {
                        "material_id": "mvtec_ad_official_page",
                        "title": "MVTec official page fixture",
                        "source_uri": str(official),
                        "source_kind": "local_path",
                        "scenario": "mvtec",
                        "material_type": "webpage",
                        "metadata": {"source_pack_role": "official_dataset_context"},
                    },
                    {
                        "material_id": "ds_mvtec_dataset_card",
                        "title": "DS-MVTec dataset card fixture",
                        "source_uri": str(dataset_card),
                        "source_kind": "local_path",
                        "scenario": "mvtec",
                        "material_type": "markdown",
                        "metadata": {"source_pack_role": "dataset_defect_label_context"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return pack
