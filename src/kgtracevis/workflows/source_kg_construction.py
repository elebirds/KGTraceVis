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
    StructuredRecordExtractor,
    TepRcaGraphExtractor,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    run_kg_construction,
)

DEFAULT_SOURCE_KG_BUILD_DIR = Path("runs/source_kg_build")
SOURCE_TEXT_FORMATS = ("csv", "json", "jsonl")
SourceTextFormat = Literal["csv", "json", "jsonl"]


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
    semantic_layer_manifest_path: Path
    rca_view_manifest_path: Path
    review_queue_path: Path
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
    nodes_path, edges_path = result.export_csv(config.output_dir)
    layer_artifacts = result.write_layer_artifacts(config.output_dir)
    summary_path = config.output_dir / "kg_construction_summary.json"
    manifest_path = config.output_dir / "kg_construction_manifest.json"
    summary = {
        **result.summary,
        "claim_boundary": (
            "source-to-KG outputs are candidate/reviewable KG rows; they are not "
            "published to Neo4j automatically"
        ),
        "output": {
            "output_dir": str(config.output_dir),
            "nodes": str(nodes_path),
            "edges": str(edges_path),
            "draft_manifest": str(layer_artifacts["draft_manifest"]),
            "semantic_layer_manifest": str(layer_artifacts["semantic_layer_manifest"]),
            "rca_view_manifest": str(layer_artifacts["rca_view_manifest"]),
            "review_queue": str(layer_artifacts["review_queue"]),
            "summary": str(summary_path),
            "manifest": str(manifest_path),
        },
        "layer_manifests": {
            "draft": result.draft_manifest(),
            "semantic_layer": result.semantic_layer.manifest,
            "rca_view": result.rca_view.manifest,
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths = {
        "output_dir": config.output_dir,
        "nodes": nodes_path,
        "edges": edges_path,
        **layer_artifacts,
        "summary": summary_path,
        "manifest": manifest_path,
    }
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
        semantic_layer_manifest_path=layer_artifacts["semantic_layer_manifest"],
        rca_view_manifest_path=layer_artifacts["rca_view_manifest"],
        review_queue_path=layer_artifacts["review_queue"],
        summary=summary,
        manifest=manifest,
    )


def _runtime_extractor_registry() -> ExtractorRegistry:
    return ExtractorRegistry(
        [
            StructuredRecordExtractor(),
            TepSemanticLiftExtractor(),
            TepVariableMappingExtractor(),
            TepRcaGraphExtractor(),
        ]
    )


def _ensure_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    outputs = [
        output_dir / "nodes.csv",
        output_dir / "edges.csv",
        output_dir / "kg_construction_summary.json",
        output_dir / "kg_construction_manifest.json",
        output_dir / "draft_manifest.json",
        output_dir / "semantic_layer_manifest.json",
        output_dir / "rca_view_manifest.json",
        output_dir / "review_queue.json",
    ]
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
    if source.source_type not in {"structured_records", "manual_table"}:
        raise ValueError(
            f"source text is only supported for structured_records/manual_table: "
            f"{source.source_id}"
        )
    source_format = str(source.metadata.get("source_format") or "jsonl").lower()
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
