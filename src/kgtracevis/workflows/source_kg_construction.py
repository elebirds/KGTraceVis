"""Reusable workflow for source-to-KG construction builds."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kgtracevis.kg_construction import (
    ExtractorRegistry,
    KGConstructionManifest,
    KGConstructionSource,
    OfflineDocumentIEExtractor,
    StructuredRecordExtractor,
    TepRcaGraphExtractor,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    run_kg_construction,
)
from kgtracevis.kg_construction.models import (
    construction_output_path_payload,
    kg_construction_artifact_paths,
)
from kgtracevis.kg_construction.publish import (
    build_publish_snapshot,
    write_publish_snapshot,
)

DEFAULT_SOURCE_KG_BUILD_DIR = Path("runs/source_kg_build")
SOURCE_TEXT_FORMATS = ("csv", "json", "jsonl", "txt", "md", "html")
SourceTextFormat = Literal["csv", "json", "jsonl", "txt", "md", "html"]
DOCUMENT_TEXT_SOURCE_TYPES = {"document", "markdown", "txt", "html", "web_snapshot"}


@dataclass(frozen=True)
class SourceKGConstructionWorkflowConfig:
    """Configuration for one source-to-KG construction build."""

    output_dir: Path
    sources: tuple[KGConstructionSource, ...]
    overwrite: bool = False
    run_id: str | None = None
    allow_reviewed_overwrite: bool = False


@dataclass(frozen=True)
class SourceKGConstructionWorkflowResult:
    """Artifact envelope returned by the source-to-KG construction workflow."""

    run_id: str
    output_dir: Path
    nodes_path: Path
    edges_path: Path
    summary_path: Path
    manifest_path: Path
    draft_manifest_path: Path
    source_audit_graph_manifest_path: Path
    semantic_layer_manifest_path: Path
    rca_view_manifest_path: Path
    review_queue_path: Path
    publish_manifest_path: Path
    summary: dict[str, object]
    manifest: KGConstructionManifest


def run_source_kg_construction_workflow(
    config: SourceKGConstructionWorkflowConfig,
    *,
    registry: ExtractorRegistry | None = None,
) -> SourceKGConstructionWorkflowResult:
    """Run source-constrained KG construction and write candidate artifacts."""
    if not config.sources:
        raise ValueError("at least one KG construction source is required")

    _ensure_output_dir(config.output_dir, overwrite=config.overwrite)
    sources = tuple(
        _materialize_text_source(source, config.output_dir) for source in config.sources
    )
    result = run_kg_construction(
        sources,
        registry=registry or _runtime_extractor_registry(),
        allow_reviewed_overwrite=config.allow_reviewed_overwrite,
        run_id=config.run_id,
    )
    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    nodes_path, edges_path = result.export_csv(config.output_dir)
    layer_artifacts = result.write_layer_artifacts(config.output_dir)
    artifact_paths["review_decisions"].parent.mkdir(parents=True, exist_ok=True)
    artifact_paths["review_decisions"].touch(exist_ok=True)
    publish_snapshot = build_publish_snapshot(
        kg_build_id=result.run_id,
        nodes=result.nodes,
        edges=result.edges,
    )
    published_nodes_path, published_edges_path, publish_report_path = write_publish_snapshot(
        publish_snapshot,
        nodes_path=artifact_paths["published_nodes"],
        edges_path=artifact_paths["published_edges"],
        report_path=artifact_paths["publish_report"],
    )
    artifact_paths.update(
        {
            "nodes": nodes_path,
            "edges": edges_path,
            "published_nodes": published_nodes_path,
            "published_edges": published_edges_path,
            "publish_report": publish_report_path,
            **layer_artifacts,
        }
    )
    summary_path = artifact_paths["summary"]
    manifest_path = artifact_paths["manifest"]
    summary = {
        **result.summary,
        "kg_build_id": result.publish_manifest.kg_build_id,
        "source_ids": list(result.publish_manifest.source_ids),
        "extractor_versions": dict(result.publish_manifest.extractor_versions),
        "profile_version": result.publish_manifest.profile_version,
        "review_policy": result.publish_manifest.review_policy,
        "claim_boundary": (
            "source-to-KG outputs are candidate/reviewable KG rows; they are not "
            "published to Neo4j automatically"
        ),
        "output": construction_output_path_payload(
            output_dir=config.output_dir,
            artifact_paths=artifact_paths,
        ),
        "layer_manifests": {
            "draft": result.draft_manifest(),
            "source_audit_graph": result.audit_graph.manifest(),
            "semantic_layer": result.semantic_layer.manifest,
            "rca_view": result.rca_view.manifest,
            "publish": result.publish_manifest.model_dump(),
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["output_dir"] = config.output_dir
    manifest = result.manifest(artifact_paths=artifact_paths)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return SourceKGConstructionWorkflowResult(
        run_id=result.run_id,
        output_dir=config.output_dir,
        nodes_path=nodes_path,
        edges_path=edges_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        draft_manifest_path=layer_artifacts["draft_manifest"],
        source_audit_graph_manifest_path=layer_artifacts["source_audit_graph_manifest"],
        semantic_layer_manifest_path=layer_artifacts["semantic_layer_manifest"],
        rca_view_manifest_path=layer_artifacts["rca_view_manifest"],
        review_queue_path=layer_artifacts["review_queue"],
        publish_manifest_path=layer_artifacts["publish_manifest"],
        summary=summary,
        manifest=manifest,
    )


def _runtime_extractor_registry() -> ExtractorRegistry:
    return ExtractorRegistry(
        [
            StructuredRecordExtractor(),
            OfflineDocumentIEExtractor(),
            TepSemanticLiftExtractor(),
            TepVariableMappingExtractor(),
            TepRcaGraphExtractor(),
        ]
    )


def _ensure_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    outputs = list(kg_construction_artifact_paths(output_dir).values())
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        paths = ", ".join(str(path) for path in existing)
        raise ValueError(f"output files already exist; pass overwrite=true to replace: {paths}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _materialize_text_source(
    source: KGConstructionSource,
    output_dir: Path,
) -> KGConstructionSource:
    if source.text is None:
        return source
    if source.path is not None:
        raise ValueError(f"{source.source_id} cannot set both path and source text")
    source_types_with_inline_text = {
        "structured_records",
        "manual_table",
        *DOCUMENT_TEXT_SOURCE_TYPES,
    }
    if source.source_type not in source_types_with_inline_text:
        raise ValueError(
            f"source text is only supported for structured_records/manual_table/document: "
            f"{source.source_id}"
        )
    default_format = "jsonl"
    if source.source_type in DOCUMENT_TEXT_SOURCE_TYPES:
        default_format = "html" if source.source_type == "html" else "txt"
    source_format = str(source.metadata.get("source_format") or default_format).lower()
    if source_format not in SOURCE_TEXT_FORMATS:
        supported = ", ".join(SOURCE_TEXT_FORMATS)
        raise ValueError(f"unsupported source_format={source_format!r}; expected {supported}")

    source_dir = output_dir / "_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{_safe_filename(source.source_id)}.{source_format}"
    source_path.write_text(source.text, encoding="utf-8")
    metadata = dict(source.metadata)
    metadata["materialized_source_text_path"] = source_path
    return KGConstructionSource(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        path=source_path,
        metadata=metadata,
    )


def _safe_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return slug or "source"
