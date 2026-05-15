"""Service wrapper for direct material-library KG construction builds."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.service import kg_construction as kg_construction_service
from kgtracevis.service.kg_materials import KGMaterialDirectBuildRequest
from kgtracevis.workflows.material_kg_construction import (
    MaterialKGConstructionWorkflowConfig,
    run_material_kg_construction_workflow,
)


class KGMaterialBuildResponse(BaseModel):
    """Response envelope for a direct material-library KG construction build."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["built"] = "built"
    run_id: str
    output_dir: str
    nodes_path: str
    edges_path: str
    published_nodes_path: str
    published_edges_path: str
    summary_path: str
    manifest_path: str
    source_library_manifest_path: str
    draft_manifest_path: str
    source_audit_graph_manifest_path: str
    semantic_layer_manifest_path: str
    rca_view_manifest_path: str
    review_queue_path: str
    review_decisions_path: str
    publish_manifest_path: str
    publish_report_path: str
    diff_path: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, Any]
    manifest: dict[str, Any]
    material_root: str
    material_ids: list[str]
    materials: list[dict[str, Any]]
    source_ids: list[str]
    extraction_results: list[dict[str, Any]]
    claim_boundary: str = (
        "material-derived KG rows are source-grounded candidates for review; "
        "direct builds do not publish to Neo4j or verify industrial facts"
    )


def run_kg_material_build(
    request: KGMaterialDirectBuildRequest,
    *,
    output_root: Path | None = None,
    material_root: Path | None = None,
) -> KGMaterialBuildResponse:
    """Run selected source materials through the reusable material KG workflow."""
    output_dir = (
        output_root or kg_construction_service.DEFAULT_SOURCE_KG_BUILD_DIR
    ) / kg_construction_service.safe_output_name(request.output_name)
    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=tuple(request.material_ids),
            output_dir=output_dir,
            material_root=material_root,
            overwrite=request.overwrite,
            run_id=request.run_id,
            extraction_mode=request.extraction_mode,
            extraction_request=request.extraction_request,
            source_type=request.source_type,
        )
    )
    return KGMaterialBuildResponse(
        run_id=result.run_id,
        output_dir=str(result.output_dir),
        nodes_path=str(result.nodes_path),
        edges_path=str(result.edges_path),
        published_nodes_path=str(result.published_nodes_path),
        published_edges_path=str(result.published_edges_path),
        summary_path=str(result.summary_path),
        manifest_path=str(result.manifest_path),
        source_library_manifest_path=str(result.source_library_manifest_path),
        draft_manifest_path=str(result.draft_manifest_path),
        source_audit_graph_manifest_path=str(result.source_audit_graph_manifest_path),
        semantic_layer_manifest_path=str(result.semantic_layer_manifest_path),
        rca_view_manifest_path=str(result.rca_view_manifest_path),
        review_queue_path=str(result.review_queue_path),
        review_decisions_path=str(result.review_decisions_path),
        publish_manifest_path=str(result.publish_manifest_path),
        publish_report_path=str(result.publish_report_path),
        diff_path=str(result.diff_path),
        artifacts=result.artifacts,
        summary=result.summary,
        manifest=result.manifest.model_dump(mode="json"),
        material_root=str(result.material_root),
        material_ids=list(result.material_ids),
        materials=[material.model_dump(mode="json") for material in result.materials],
        source_ids=[source.source_id for source in result.sources],
        extraction_results=[
            extraction.model_dump(mode="json") for extraction in result.extraction_results
        ],
    )
