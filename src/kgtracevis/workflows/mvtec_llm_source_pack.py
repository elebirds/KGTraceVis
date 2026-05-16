"""Build MVTec source packs for LLM-assisted KG construction evaluation."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MaterialType = Literal["pdf", "webpage", "text", "markdown", "other"]

DEFAULT_MVTEC_SOURCE_BUNDLE_DIR = Path("docs/sources/mvtec_source_bundle")
DEFAULT_DEFECT_SPECTRUM_DIR = Path("data/external/Defect_Spectrum")

EXCLUDED_DERIVED_SOURCE_NAMES = (
    "domain_knowledge.json",
    "mvtec_ad_catalog.csv",
    "mvtec_ad_kg.ttl",
    "mvtec_ad_best_prompt.md",
    "mvtec_ad_evidence_matrix.md",
    "mvtec_follow_chip_pattern_coverage.csv",
    "mvtec_follow_chip_pattern_enhanced.csv",
    "mvtec_follow_chip_pattern_nodes.csv",
    "mvtec_follow_chip_pattern_strict.csv",
)


@dataclass(frozen=True)
class MVTecSourceMaterialSpec:
    """One raw or near-raw material candidate for the MVTec LLM source pack."""

    material_id: str
    title: str
    path: Path
    material_type: MaterialType
    provenance_role: str


@dataclass(frozen=True)
class MVTecLLMSourcePackConfig:
    """Configuration for building an MVTec LLM construction source pack."""

    output_dir: Path
    mvtec_source_bundle_dir: Path = DEFAULT_MVTEC_SOURCE_BUNDLE_DIR
    defect_spectrum_dir: Path = DEFAULT_DEFECT_SPECTRUM_DIR
    overwrite: bool = False
    include_patchcore: bool = True


@dataclass(frozen=True)
class MVTecLLMSourcePackResult:
    """Result paths and payload for one MVTec LLM source pack."""

    output_dir: Path
    source_pack_path: Path
    material_manifest_path: Path
    copied_source_dir: Path
    material_count: int
    manifest: dict[str, Any]


def build_mvtec_llm_source_pack(
    config: MVTecLLMSourcePackConfig,
) -> MVTecLLMSourcePackResult:
    """Copy allowed MVTec source materials and write a material registration manifest."""
    if config.output_dir.exists() and any(config.output_dir.iterdir()) and not config.overwrite:
        raise ValueError(f"{config.output_dir} already exists; pass overwrite=true to replace")
    if config.output_dir.exists() and config.overwrite:
        shutil.rmtree(config.output_dir)
    source_dir = config.output_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    materials: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for spec in _default_material_specs(config):
        if not spec.path.is_file():
            skipped.append(
                {
                    "material_id": spec.material_id,
                    "path": str(spec.path),
                    "reason": "missing",
                }
            )
            continue
        copied_path = _copy_material_source(spec, source_dir)
        materials.append(_material_registration_payload(spec, copied_path))

    if not materials:
        raise ValueError(
            "no MVTec source materials found; expected official page, DS-MVTec "
            "dataset card, or source bundle files"
        )

    manifest = {
        "artifact_type": "mvtec_llm_source_pack_v1",
        "claim_boundary": (
            "MVTec source materials may support visual anomaly KG candidates and "
            "reviewable hypotheses; they do not provide verified factory RCA labels"
        ),
        "construction_goal": (
            "raw/near-raw documents -> document understanding -> chunk IE -> "
            "brainstorming -> reviewable KG candidates"
        ),
        "source_policy": {
            "allowed": (
                "official pages, paper/source-bundle snapshots, dataset cards, "
                "and prose documentation"
            ),
            "excluded": (
                "prebuilt KG files, generated catalogs, domain_knowledge JSON, "
                "prompt files, and generated node/edge tables"
            ),
        },
        "excluded_derived_sources": list(EXCLUDED_DERIVED_SOURCE_NAMES),
        "materials": materials,
        "skipped": skipped,
    }
    source_pack_path = config.output_dir / "mvtec_llm_source_pack.json"
    material_manifest_path = config.output_dir / "material_registration.json"
    _write_json(source_pack_path, manifest)
    _write_json(
        material_manifest_path,
        {
            "artifact_type": "kg_material_registration_manifest_v1",
            "materials": materials,
        },
    )
    return MVTecLLMSourcePackResult(
        output_dir=config.output_dir,
        source_pack_path=source_pack_path,
        material_manifest_path=material_manifest_path,
        copied_source_dir=source_dir,
        material_count=len(materials),
        manifest=manifest,
    )


def _default_material_specs(
    config: MVTecLLMSourcePackConfig,
) -> tuple[MVTecSourceMaterialSpec, ...]:
    specs = [
        MVTecSourceMaterialSpec(
            material_id="mvtec_ad_official_page",
            title="MVTec AD official dataset page snapshot",
            path=config.mvtec_source_bundle_dir / "mvtec_ad_official_page.html",
            material_type="webpage",
            provenance_role="official_dataset_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="ds_mvtec_dataset_card",
            title="DS-MVTec dataset card",
            path=config.defect_spectrum_dir / "DS-MVTec" / "DS-MVTec.md",
            material_type="markdown",
            provenance_role="dataset_defect_label_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="mvtec_ad_paper_pdf",
            title="MVTec AD CVPR dataset paper PDF",
            path=config.mvtec_source_bundle_dir / "raw" / "mvtec_ad_cvpr_2019.pdf",
            material_type="pdf",
            provenance_role="official_dataset_paper_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="visual_defect_survey_html",
            title="Visual-based defect detection and classification survey",
            path=config.mvtec_source_bundle_dir / "visual_defect_survey_mdpi.html",
            material_type="webpage",
            provenance_role="industrial_visual_defect_taxonomy_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="injection_molding_root_causes_pdf",
            title="Injection molding defect root-cause paper",
            path=(
                config.mvtec_source_bundle_dir
                / "raw"
                / "injection_molding_root_causes.pdf"
            ),
            material_type="pdf",
            provenance_role="manufacturing_process_root_cause_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="injection_molding_defects_chart_pdf",
            title="Plastic injection molding defects chart",
            path=(
                config.mvtec_source_bundle_dir
                / "raw"
                / "plastic_injection_molding_defects_chart.pdf"
            ),
            material_type="pdf",
            provenance_role="manufacturing_defect_cause_table_context",
        ),
        MVTecSourceMaterialSpec(
            material_id="mvtec_source_bundle_readme",
            title="MVTec source bundle README",
            path=config.mvtec_source_bundle_dir / "README.md",
            material_type="markdown",
            provenance_role="source_provenance_context",
        ),
    ]
    if config.include_patchcore:
        specs.append(
            MVTecSourceMaterialSpec(
                material_id="patchcore_arxiv_abs",
                title="PatchCore arXiv abstract snapshot",
                path=config.mvtec_source_bundle_dir / "patchcore_arxiv_abs.html",
                material_type="webpage",
                provenance_role="model_evidence_boundary_context",
            )
        )
    return tuple(specs)


def _copy_material_source(spec: MVTecSourceMaterialSpec, source_dir: Path) -> Path:
    suffix = "".join(spec.path.suffixes) or ".txt"
    destination = source_dir / f"{spec.material_id}{suffix}"
    shutil.copyfile(spec.path, destination)
    return destination


def _material_registration_payload(
    spec: MVTecSourceMaterialSpec,
    copied_path: Path,
) -> dict[str, Any]:
    return {
        "material_id": spec.material_id,
        "title": spec.title,
        "source_uri": str(copied_path),
        "source_kind": "local_path",
        "scenario": "mvtec",
        "material_type": spec.material_type,
        "metadata": {
            "source_pack_role": spec.provenance_role,
            "original_path": str(spec.path),
            "source_pack_policy": "raw_or_near_raw_material_only",
            "excludes_prebuilt_kg": True,
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
