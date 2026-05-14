"""Service DTOs and handlers for source-to-KG construction builds."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.workflows.source_kg_construction import (
    DEFAULT_SOURCE_KG_BUILD_DIR,
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)

ConstructionSourceType = Literal[
    "structured_records",
    "manual_table",
    "tep_semantic_lift",
    "tep_variable_mapping",
]
ConstructionSourceFormat = Literal["csv", "json", "jsonl"]


class KGConstructionSourceInput(BaseModel):
    """One supported source input for a construction build request."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: ConstructionSourceType
    scenario: str = "shared"
    path: str | None = None
    source_text: str | None = None
    source_format: ConstructionSourceFormat = "jsonl"
    semantic_nodes_path: str | None = None
    semantic_edges_path: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_supported_shape(self) -> KGConstructionSourceInput:
        """Constrain runtime construction to explicit safe source shapes."""
        if self.source_type in {"structured_records", "manual_table"}:
            if not self.path and self.source_text is None:
                raise ValueError(
                    "structured_records/manual_table sources require path or source_text"
                )
            if self.path and self.source_text is not None:
                raise ValueError("pass either path or source_text, not both")
            return self
        if self.source_type == "tep_semantic_lift":
            has_pair = bool(self.semantic_nodes_path and self.semantic_edges_path)
            if not self.path and not has_pair:
                raise ValueError(
                    "tep_semantic_lift requires path or semantic_nodes_path/"
                    "semantic_edges_path"
                )
            if bool(self.semantic_nodes_path) != bool(self.semantic_edges_path):
                raise ValueError(
                    "semantic_nodes_path and semantic_edges_path must be provided together"
                )
            if self.source_text is not None:
                raise ValueError("tep_semantic_lift does not accept source_text")
            return self
        if self.source_type == "tep_variable_mapping":
            if not self.path:
                raise ValueError("tep_variable_mapping requires path")
            if self.source_text is not None:
                raise ValueError("tep_variable_mapping does not accept source_text")
            return self
        raise ValueError(f"unsupported source_type={self.source_type}")


class KGConstructionBuildRequest(BaseModel):
    """Request to run a source-to-KG construction build."""

    model_config = ConfigDict(extra="forbid")

    sources: list[KGConstructionSourceInput]
    output_name: str = "runtime"
    overwrite: bool = False
    run_id: str | None = None


class KGConstructionBuildResponse(BaseModel):
    """Response envelope for a completed source-to-KG build."""

    model_config = ConfigDict(extra="forbid")

    status: str
    run_id: str
    output_dir: str
    nodes_path: str
    edges_path: str
    summary_path: str
    manifest_path: str
    summary: dict[str, object]
    claim_boundary: str = (
        "source-to-KG outputs are candidate/reviewable KG rows; they are not "
        "published to Neo4j automatically"
    )


def run_kg_construction_build(
    request: KGConstructionBuildRequest,
    *,
    output_root: Path | None = None,
) -> KGConstructionBuildResponse:
    """Run a construction build from a narrow API-safe request."""
    sources = tuple(_source_from_input(source) for source in request.sources)
    output_dir = (output_root or DEFAULT_SOURCE_KG_BUILD_DIR) / _safe_output_name(
        request.output_name
    )
    result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=output_dir,
            sources=sources,
            overwrite=request.overwrite,
            run_id=request.run_id,
        )
    )
    return KGConstructionBuildResponse(
        status="built",
        run_id=result.run_id,
        output_dir=str(result.output_dir),
        nodes_path=str(result.nodes_path),
        edges_path=str(result.edges_path),
        summary_path=str(result.summary_path),
        manifest_path=str(result.manifest_path),
        summary=result.summary,
    )


def _source_from_input(source: KGConstructionSourceInput) -> KGConstructionSource:
    metadata = dict(source.metadata)
    path = Path(source.path) if source.path else None
    if source.source_text is not None:
        metadata["source_format"] = source.source_format
    if source.source_type == "tep_semantic_lift":
        if source.semantic_nodes_path and source.semantic_edges_path:
            metadata["nodes_path"] = Path(source.semantic_nodes_path)
            metadata["edges_path"] = Path(source.semantic_edges_path)
    return KGConstructionSource(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        path=path,
        text=source.source_text,
        metadata=metadata,
    )


def _safe_output_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("output_name cannot be empty")
    if Path(stripped).is_absolute() or ".." in Path(stripped).parts:
        raise ValueError("output_name must be a relative directory name")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stripped).strip("._")
    if not safe:
        raise ValueError("output_name must contain at least one safe filename character")
    if safe != stripped:
        raise ValueError("output_name may contain only letters, numbers, '.', '_', and '-'")
    return safe


__all__ = [
    "KGConstructionBuildRequest",
    "KGConstructionBuildResponse",
    "KGConstructionSourceInput",
    "run_kg_construction_build",
]
