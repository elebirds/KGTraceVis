"""Reusable workflow for material-library driven KG construction builds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kgtracevis.kg_construction import KGConstructionManifest, KGConstructionSource
from kgtracevis.kg_construction.document_extraction import DocumentIEClient
from kgtracevis.service.kg_construction import KGConstructionSourceInput
from kgtracevis.service.kg_materials import (
    DEFAULT_SOURCE_KG_MATERIAL_DIR,
    KGMaterialExtractionRunRequest,
    KGMaterialExtractionRunResponse,
    KGMaterialRecord,
    KGMaterialSelectedBuildRequest,
    extract_kg_material_to_structured_records,
    get_kg_material,
    prepare_kg_material_construction_build,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)

MaterialExtractionMode = Literal["never", "missing", "always"]


@dataclass(frozen=True)
class MaterialKGConstructionWorkflowConfig:
    """Configuration for one material-library KG construction build."""

    material_ids: tuple[str, ...]
    output_dir: Path
    material_root: Path | None = None
    overwrite: bool = False
    run_id: str | None = None
    extraction_mode: MaterialExtractionMode = "never"
    extraction_request: KGMaterialExtractionRunRequest | None = None
    source_type: Literal["structured_records", "manual_table"] = "structured_records"
    allow_reviewed_overwrite: bool = False


@dataclass(frozen=True)
class MaterialKGConstructionWorkflowResult:
    """Artifact envelope returned by the material KG construction workflow."""

    run_id: str
    output_dir: Path
    nodes_path: Path
    edges_path: Path
    summary_path: Path
    manifest_path: Path
    summary: dict[str, object]
    manifest: KGConstructionManifest
    material_root: Path
    material_ids: tuple[str, ...]
    materials: tuple[KGMaterialRecord, ...]
    sources: tuple[KGConstructionSource, ...]
    extraction_results: tuple[KGMaterialExtractionRunResponse, ...]


def run_material_kg_construction_workflow(
    config: MaterialKGConstructionWorkflowConfig,
    *,
    client: DocumentIEClient | None = None,
) -> MaterialKGConstructionWorkflowResult:
    """Build candidate KG artifacts from selected material-library records."""
    _validate_material_selection(config.material_ids)
    material_root = config.material_root or DEFAULT_SOURCE_KG_MATERIAL_DIR
    extraction_results = _extract_selected_materials(config, client=client)
    build_sources = prepare_kg_material_construction_build(
        KGMaterialSelectedBuildRequest(
            material_ids=list(config.material_ids),
            output_name=config.output_dir.name,
            overwrite=config.overwrite,
            run_id=config.run_id,
            source_type=config.source_type,
        ),
        material_root=material_root,
    )
    sources = tuple(_source_from_material_input(source) for source in build_sources.sources)
    build_result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=config.output_dir,
            sources=sources,
            overwrite=config.overwrite,
            run_id=config.run_id,
            allow_reviewed_overwrite=config.allow_reviewed_overwrite,
        )
    )
    summary = _material_summary(
        build_result.summary,
        materials=tuple(build_sources.materials),
        sources=sources,
        extraction_mode=config.extraction_mode,
        extraction_results=extraction_results,
        material_root=material_root,
    )
    build_result.summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return MaterialKGConstructionWorkflowResult(
        run_id=build_result.run_id,
        output_dir=build_result.output_dir,
        nodes_path=build_result.nodes_path,
        edges_path=build_result.edges_path,
        summary_path=build_result.summary_path,
        manifest_path=build_result.manifest_path,
        summary=summary,
        manifest=build_result.manifest,
        material_root=material_root,
        material_ids=config.material_ids,
        materials=tuple(build_sources.materials),
        sources=sources,
        extraction_results=extraction_results,
    )


def _extract_selected_materials(
    config: MaterialKGConstructionWorkflowConfig,
    *,
    client: DocumentIEClient | None,
) -> tuple[KGMaterialExtractionRunResponse, ...]:
    if config.extraction_mode == "never":
        return ()
    if config.extraction_mode not in {"missing", "always"}:
        raise ValueError(
            "extraction_mode must be one of 'never', 'missing', or 'always'"
        )

    request = config.extraction_request or KGMaterialExtractionRunRequest()
    results: list[KGMaterialExtractionRunResponse] = []
    for material_id in config.material_ids:
        material = get_kg_material(material_id, material_root=config.material_root).material
        if config.extraction_mode == "missing" and material.is_build_ready:
            continue
        results.append(
            extract_kg_material_to_structured_records(
                material_id,
                request,
                client=client,
                material_root=config.material_root,
            )
        )
    return tuple(results)


def _source_from_material_input(source: KGConstructionSourceInput) -> KGConstructionSource:
    metadata = dict(source.metadata)
    path = Path(source.path) if source.path else None
    if source.source_text is not None:
        metadata["source_format"] = source.source_format
    return KGConstructionSource(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        path=path,
        text=source.source_text,
        metadata=metadata,
    )


def _material_summary(
    base_summary: dict[str, object],
    *,
    materials: tuple[KGMaterialRecord, ...],
    sources: tuple[KGConstructionSource, ...],
    extraction_mode: MaterialExtractionMode,
    extraction_results: tuple[KGMaterialExtractionRunResponse, ...],
    material_root: Path,
) -> dict[str, object]:
    summary = dict(base_summary)
    summary["material_library"] = {
        "material_root": str(material_root),
        "material_count": len(materials),
        "material_ids": [material.material_id for material in materials],
        "source_ids": [source.source_id for source in sources],
        "extraction_mode": extraction_mode,
        "extracted_material_ids": [
            result.material.material_id for result in extraction_results
        ],
        "claim_boundary": (
            "material-derived KG rows are source-grounded candidates for review; "
            "selection or extraction does not verify industrial facts or publish to Neo4j"
        ),
    }
    return summary


def _validate_material_selection(material_ids: tuple[str, ...]) -> None:
    if not material_ids:
        raise ValueError("material_ids must contain at least one material_id")
