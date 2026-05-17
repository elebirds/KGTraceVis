"""Direct material-library builds over the existing construction service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.service.kg_construction import run_kg_construction_build
from kgtracevis.service.kg_materials import (
    KGMaterialDirectBuildRequest,
    KGMaterialExtractionRunRequest,
    extract_kg_material_to_structured_records,
    get_kg_material,
    prepare_kg_material_construction_build,
)


class KGMaterialBuildResponse(BaseModel):
    """Response envelope for a direct material-library construction build."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["built"] = "built"
    run_id: str
    output_dir: str
    nodes_path: str
    edges_path: str
    summary_path: str
    manifest_path: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, Any]
    material_root: str
    material_ids: list[str]
    materials: list[dict[str, Any]]
    source_ids: list[str]
    construction_build: dict[str, Any]
    claim_boundary: str = (
        "material-derived KG rows are candidate/reviewable construction outputs; "
        "they do not verify industrial facts automatically"
    )


def run_kg_material_build(
    request: KGMaterialDirectBuildRequest,
    *,
    output_root: Path | None = None,
    material_root: Path | None = None,
) -> KGMaterialBuildResponse:
    """Build selected materials, optionally extracting structured records first."""
    if request.extraction_mode in {"missing", "always"}:
        extraction_request = request.extraction_request or KGMaterialExtractionRunRequest(
            overwrite=True,
        )
        for material_id in request.material_ids:
            material = get_kg_material(material_id, material_root=material_root).material
            if request.extraction_mode == "always" or not material.is_build_ready:
                extract_kg_material_to_structured_records(
                    material_id,
                    extraction_request,
                    material_root=material_root,
                )

    build_sources = prepare_kg_material_construction_build(request, material_root=material_root)
    build = run_kg_construction_build(
        build_sources.construction_request,
        output_root=output_root,
    )
    artifacts = {
        "nodes": build.nodes_path,
        "edges": build.edges_path,
        "summary": build.summary_path,
        "manifest": build.manifest_path,
    }
    for key in (
        "source_units_path",
        "knowledge_cards_path",
        "entities_path",
        "validation_report_path",
        "domain_profiles_path",
        "domain_profile_report_path",
        "domain_profiles_manifest_path",
        "runtime_views_manifest_path",
    ):
        value = getattr(build, key, None)
        if value:
            artifacts[key.removesuffix('_path')] = str(value)
    return KGMaterialBuildResponse(
        run_id=build.run_id,
        output_dir=build.output_dir,
        nodes_path=build.nodes_path,
        edges_path=build.edges_path,
        summary_path=build.summary_path,
        manifest_path=build.manifest_path,
        artifacts=artifacts,
        summary=dict(build.summary),
        material_root=build_sources.material_root,
        material_ids=list(request.material_ids),
        materials=[material.model_dump(mode="json") for material in build_sources.materials],
        source_ids=[source.source_id for source in build_sources.sources],
        construction_build=build.model_dump(mode="json"),
    )


__all__ = ["KGMaterialBuildResponse", "run_kg_material_build"]
