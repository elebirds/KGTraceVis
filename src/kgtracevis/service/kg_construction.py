"""Service DTOs and handlers for source-to-KG construction builds."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.workflows.source_kg_construction import (
    DEFAULT_SOURCE_KG_BUILD_DIR,
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)

DEFAULT_SOURCE_KG_SOURCE_DIR = Path("runs/source_kg_sources")
MAX_SOURCE_UPLOAD_BYTES = 5_000_000
ConstructionSourceType = Literal[
    "structured_records",
    "manual_table",
    "tep_semantic_lift",
    "tep_variable_mapping",
]
ConstructionSourceFormat = Literal["csv", "json", "jsonl"]
SOURCE_UPLOAD_FORMATS: dict[str, ConstructionSourceFormat] = {
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
}


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


class KGConstructionSourceUploadRequest(BaseModel):
    """Metadata for a construction source file upload."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: ConstructionSourceType = "manual_table"
    scenario: str = "shared"
    source_format: ConstructionSourceFormat
    filename: str

    @model_validator(mode="after")
    def validate_upload_shape(self) -> KGConstructionSourceUploadRequest:
        """Validate source uploads before bytes are persisted."""
        _safe_path_component(self.source_id, field_name="source_id")
        if self.source_type == "tep_semantic_lift":
            raise ValueError(
                "tep_semantic_lift upload requires a multi-file bundle; "
                "register explicit semantic nodes/edges paths for now"
            )
        if not self.scenario.strip():
            raise ValueError("scenario cannot be empty")
        expected_format = _source_format_from_filename(self.filename)
        if expected_format != self.source_format:
            raise ValueError(
                f"filename extension implies source_format={expected_format}; "
                f"received source_format={self.source_format}"
            )
        return self


class KGConstructionUploadedSource(BaseModel):
    """Stored construction source metadata returned by the upload API."""

    model_config = ConfigDict(extra="forbid")

    status: str = "uploaded"
    source_id: str
    source_type: ConstructionSourceType
    scenario: str
    source_format: ConstructionSourceFormat
    filename: str
    path: str
    metadata_path: str
    size_bytes: int
    uploaded_at: str
    build_source: KGConstructionSourceInput
    claim_boundary: str = (
        "uploaded sources are construction inputs only; they do not mutate KG "
        "artifacts or Neo4j until an explicit build/import step runs"
    )


class KGConstructionSourceListResponse(BaseModel):
    """List response for uploaded construction source artifacts."""

    model_config = ConfigDict(extra="forbid")

    source_root: str
    sources: list[KGConstructionUploadedSource]


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


def save_kg_construction_source_upload(
    *,
    source_id: str,
    source_type: ConstructionSourceType,
    scenario: str,
    filename: str,
    content: bytes,
    source_format: ConstructionSourceFormat | None = None,
    source_root: Path | None = None,
) -> KGConstructionUploadedSource:
    """Persist an uploaded source artifact and return a build-ready reference."""
    resolved_format = source_format or _source_format_from_filename(filename)
    request = KGConstructionSourceUploadRequest(
        source_id=source_id,
        source_type=source_type,
        scenario=scenario,
        source_format=resolved_format,
        filename=filename,
    )
    if not content:
        raise ValueError("uploaded source file cannot be empty")
    if len(content) > MAX_SOURCE_UPLOAD_BYTES:
        raise ValueError(
            f"uploaded source file exceeds {MAX_SOURCE_UPLOAD_BYTES} bytes: {len(content)}"
        )

    root = source_root or DEFAULT_SOURCE_KG_SOURCE_DIR
    source_dir = root / _safe_path_component(request.source_id, field_name="source_id")
    source_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = _safe_upload_filename(request.filename)
    source_path = source_dir / stored_filename
    metadata_path = source_dir / "metadata.json"
    source_path.write_bytes(content)

    uploaded_at = datetime.now(UTC).isoformat()
    build_source = KGConstructionSourceInput(
        source_id=request.source_id,
        source_type=request.source_type,
        scenario=request.scenario,
        path=str(source_path),
        source_format=request.source_format,
        metadata={
            "uploaded_at": uploaded_at,
            "uploaded_filename": request.filename,
            "source_upload_path": str(source_path),
        },
    )
    uploaded = KGConstructionUploadedSource(
        source_id=request.source_id,
        source_type=request.source_type,
        scenario=request.scenario,
        source_format=request.source_format,
        filename=request.filename,
        path=str(source_path),
        metadata_path=str(metadata_path),
        size_bytes=len(content),
        uploaded_at=uploaded_at,
        build_source=build_source,
    )
    metadata_path.write_text(
        json.dumps(uploaded.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return uploaded


def list_kg_construction_source_uploads(
    *,
    source_root: Path | None = None,
) -> KGConstructionSourceListResponse:
    """List stored construction source uploads from the runtime source directory."""
    root = source_root or DEFAULT_SOURCE_KG_SOURCE_DIR
    if not root.exists():
        return KGConstructionSourceListResponse(source_root=str(root), sources=[])
    sources: list[KGConstructionUploadedSource] = []
    for metadata_path in sorted(root.glob("*/metadata.json")):
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        sources.append(KGConstructionUploadedSource.model_validate(payload))
    sources.sort(key=lambda item: item.uploaded_at, reverse=True)
    return KGConstructionSourceListResponse(source_root=str(root), sources=sources)


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


def _source_format_from_filename(filename: str) -> ConstructionSourceFormat:
    suffix = Path(filename).suffix.lower()
    source_format = SOURCE_UPLOAD_FORMATS.get(suffix)
    if source_format is None:
        supported = ", ".join(sorted(SOURCE_UPLOAD_FORMATS))
        raise ValueError(f"source upload filename must end with one of: {supported}")
    return source_format


def _safe_path_component(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    if Path(stripped).name != stripped:
        raise ValueError(f"{field_name} must be a single path component")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stripped).strip("._")
    if safe != stripped or not safe:
        raise ValueError(
            f"{field_name} may contain only letters, numbers, '.', '_', and '-'"
        )
    return safe


def _safe_upload_filename(filename: str) -> str:
    safe_name = _safe_path_component(Path(filename).name, field_name="filename")
    _source_format_from_filename(safe_name)
    return safe_name


__all__ = [
    "ConstructionSourceFormat",
    "ConstructionSourceType",
    "KGConstructionBuildRequest",
    "KGConstructionBuildResponse",
    "KGConstructionSourceListResponse",
    "KGConstructionSourceInput",
    "KGConstructionSourceUploadRequest",
    "KGConstructionUploadedSource",
    "list_kg_construction_source_uploads",
    "run_kg_construction_build",
    "save_kg_construction_source_upload",
]
