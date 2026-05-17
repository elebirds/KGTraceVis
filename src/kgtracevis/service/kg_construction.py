"""Service DTOs and handlers for source-to-KG construction builds."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.kg.import_neo4j import (
    DEFAULT_NEO4J_CONFIG_PATH,
    dry_run_import,
    import_knowledge_graph_with_config,
    resolve_neo4j_config,
)
from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.kg_construction.export_kg_csv import EDGE_COLUMNS
from kgtracevis.kg_construction.models import (
    KGConstructionReviewDecision,
    build_kg_construction_run_id,
    review_decision_for_edge,
)
from kgtracevis.kg_construction.qa import run_kg_qa
from kgtracevis.source_kg_compiler import (
    DEFAULT_LLM_CONCURRENCY,
    OpenAICompatibleSourceKGLLM,
    SourceKGCompilerConfig,
    run_source_kg_compiler_workflow,
)
from kgtracevis.workflows.kg_overlay_validation import (
    KGOverlayValidationConfig,
    run_kg_overlay_validation,
)
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
    "document",
    "tep_semantic_lift",
    "tep_variable_mapping",
]
ConstructionSourceFormat = Literal["csv", "json", "jsonl", "text", "markdown"]
SOURCE_UPLOAD_FORMATS: dict[str, ConstructionSourceFormat] = {
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "text",
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
        if self.source_type in {"structured_records", "manual_table", "document"}:
            if not self.path and self.source_text is None:
                kind = self.source_type
                raise ValueError(f"{kind} sources require path or source_text")
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
    llm_concurrency: int = Field(default=DEFAULT_LLM_CONCURRENCY, ge=1)

    @model_validator(mode="after")
    def validate_build_shape(self) -> KGConstructionBuildRequest:
        """Require at least one source and a safe output name."""
        if not self.sources:
            raise ValueError("sources must contain at least one source")
        _safe_output_name(self.output_name)
        return self


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
    source_units_path: str | None = None
    knowledge_cards_path: str | None = None
    entities_path: str | None = None
    validation_report_path: str | None = None
    domain_profiles_path: str | None = None
    domain_profile_report_path: str | None = None
    domain_profiles_manifest_path: str | None = None
    runtime_views_manifest_path: str | None = None
    summary: dict[str, object]
    claim_boundary: str = (
        "source-to-KG outputs are candidate/reviewable KG rows; they are not "
        "published to Neo4j automatically"
    )


class KGConstructionOverlayValidationRequest(BaseModel):
    """Request to validate one candidate build as a runtime/import overlay."""

    model_config = ConfigDict(extra="forbid")

    example_dir: str = "data/examples"
    overlay_only_runtime: bool = False
    overlay_only_import: bool = False
    top_k: int = Field(default=5, ge=1)


class KGConstructionOverlayValidationResponse(BaseModel):
    """Overlay validation response for one construction build."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    report: dict[str, Any]
    report_path: str | None = None
    claim_boundary: str = (
        "overlay validation checks candidate KG consumption and dry-run import readiness; "
        "it does not publish to Neo4j or verify industrial facts"
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
        if self.source_type in {"manual_table", "structured_records", "tep_variable_mapping"}:
            if self.source_format not in {"csv", "json", "jsonl"}:
                raise ValueError("source upload filename must end with one of: .csv, .json, .jsonl")
        if self.source_type == "document" and self.source_format not in {"text", "markdown"}:
            raise ValueError("document upload requires text or markdown source_format")
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


class KGConstructionBuildRecord(BaseModel):
    """One source-to-KG construction build registry entry."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    created_at: str | None = None
    output_dir: str
    nodes_path: str
    edges_path: str
    summary_path: str
    manifest_path: str
    source_ids: list[str] = Field(default_factory=list)
    source_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    scenarios: dict[str, int] = Field(default_factory=dict)
    review_status_counts: dict[str, int] = Field(default_factory=dict)
    claim_boundary: str = (
        "source-to-KG build registry entries are candidate/reviewable KG "
        "snapshots; they are not published to Neo4j automatically"
    )


class KGConstructionBuildListResponse(BaseModel):
    """List response for source-to-KG construction builds."""

    model_config = ConfigDict(extra="forbid")

    build_root: str
    builds: list[KGConstructionBuildRecord]


class KGConstructionBuildDetail(BaseModel):
    """Detail response for one source-to-KG construction build."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    summary: dict[str, Any]
    manifest: dict[str, Any]


class KGConstructionBuildValidationResponse(BaseModel):
    """Validation response for one source-to-KG construction build."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    qa_report: dict[str, Any]
    claim_boundary: str = (
        "validation reports KG CSV contract issues and warnings; it does not "
        "mutate KG files or publish to Neo4j"
    )


class KGConstructionPublishRequest(BaseModel):
    """Request to dry-run or explicitly publish one construction build."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    include_defaults: bool = True
    confirm_publish: bool = False
    config_path: str = str(DEFAULT_NEO4J_CONFIG_PATH)
    uri: str | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None


class KGConstructionImportSummary(BaseModel):
    """Serializable import counts returned by construction publish."""

    model_config = ConfigDict(extra="forbid")

    node_count: int
    edge_count: int
    dry_run: bool


class KGConstructionPublishResponse(BaseModel):
    """Response envelope for construction publish/dry-run."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    import_summary: KGConstructionImportSummary
    include_defaults: bool
    node_paths: list[str]
    edge_paths: list[str]
    claim_boundary: str = (
        "construction publish loads candidate/reviewable KG rows; real Neo4j "
        "writes require explicit confirmation and do not upgrade auto rows to "
        "ground truth"
    )


class KGConstructionEdgeReviewRequest(BaseModel):
    """Request to review one candidate construction KG edge."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "reject"]
    target_key: str | None = None
    head: str | None = None
    relation: str | None = None
    tail: str | None = None
    scenario: str | None = None
    reviewer: str | None = None
    note: str | None = None
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> KGConstructionEdgeReviewRequest:
        """Require exactly one stable edge target shape."""
        has_key = self.target_key is not None
        has_parts = all((self.head, self.relation, self.tail, self.scenario))
        if has_key == bool(has_parts):
            raise ValueError(
                "pass either target_key or head/relation/tail/scenario for edge review"
            )
        return self

    def edge_key(self) -> str:
        """Return the target edge key in KGEdge.edge_id format."""
        if self.target_key is not None:
            return _safe_edge_key(self.target_key)
        return _safe_edge_key(
            f"{self.head}|{self.relation}|{self.tail}|{self.scenario}"
        )


class KGConstructionEdgeReviewResponse(BaseModel):
    """Response envelope for one construction edge review action."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    decision: KGConstructionReviewDecision
    edge: dict[str, Any]
    summary: dict[str, Any]
    manifest_path: str
    edges_path: str
    claim_boundary: str = (
        "edge review updates only the selected construction build artifacts; "
        "Neo4j publication remains a separate explicit step"
    )


class KGConstructionReviewQueueRequest(BaseModel):
    """Filters and pagination for construction edge review queues."""

    model_config = ConfigDict(extra="forbid")

    review_status: Literal["auto", "reviewed", "rejected"] | None = None
    source: str | None = None
    scenario: str | None = None
    relation: str | None = None
    query: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class KGConstructionReviewQueueEdge(BaseModel):
    """One reviewable construction edge row."""

    model_config = ConfigDict(extra="forbid")

    target_key: str
    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float
    weight: float
    review_status: str
    feedback_count: int
    accepted_count: int
    rejected_count: int


class KGConstructionReviewQueueSummary(BaseModel):
    """Facet counts for a construction review queue."""

    model_config = ConfigDict(extra="forbid")

    review_status_counts: dict[str, int] = Field(default_factory=dict)
    relation_counts: dict[str, int] = Field(default_factory=dict)
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)


class KGConstructionReviewQueueResponse(BaseModel):
    """Read-only queue response for construction edge review."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    filters: KGConstructionReviewQueueRequest
    total_count: int
    returned_count: int
    offset: int
    limit: int
    edges: list[KGConstructionReviewQueueEdge]
    summary: KGConstructionReviewQueueSummary
    claim_boundary: str = (
        "review queues are read-only views over candidate construction edges; "
        "accept/reject and Neo4j publish are separate explicit actions"
    )


def run_kg_construction_build(
    request: KGConstructionBuildRequest,
    *,
    output_root: Path | None = None,
) -> KGConstructionBuildResponse:
    """Run a construction build from a narrow API-safe request."""
    output_dir = (output_root or DEFAULT_SOURCE_KG_BUILD_DIR) / _safe_output_name(
        request.output_name
    )
    if _uses_source_kg_compiler(request):
        return _run_kg_construction_compiler_build(request, output_dir=output_dir)

    sources = tuple(_source_from_input(source) for source in request.sources)
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


def list_kg_construction_builds(
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildListResponse:
    """List source-to-KG build artifacts discovered under the build root."""
    root = build_root or DEFAULT_SOURCE_KG_BUILD_DIR
    builds = [
        _build_record_from_manifest_path(manifest_path)
        for manifest_path in _build_manifest_paths(root)
    ]
    builds.sort(key=lambda item: item.created_at or "", reverse=True)
    return KGConstructionBuildListResponse(build_root=str(root), builds=builds)


def get_kg_construction_build(
    run_id: str,
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildDetail:
    """Return summary and manifest payload for one construction build."""
    build = _find_build_record(run_id, build_root=build_root)
    summary_path = Path(build.summary_path)
    manifest_path = Path(build.manifest_path)
    if not summary_path.is_file():
        raise ValueError(f"construction build summary not found: {summary_path}")
    if not manifest_path.is_file():
        raise ValueError(f"construction build manifest not found: {manifest_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"construction build summary must be an object: {summary_path}")
    if not isinstance(manifest, dict):
        raise ValueError(f"construction build manifest must be an object: {manifest_path}")
    return KGConstructionBuildDetail(build=build, summary=summary, manifest=manifest)


def get_kg_construction_build_artifact_path(
    run_id: str,
    artifact_key: str,
    *,
    build_root: Path | None = None,
) -> Path:
    """Resolve a stable artifact key for one construction build."""
    build = _find_build_record(run_id, build_root=build_root)
    output_dir = Path(build.output_dir)
    artifacts = {
        "nodes": Path(build.nodes_path),
        "edges": Path(build.edges_path),
        "summary": Path(build.summary_path),
        "manifest": Path(build.manifest_path),
        "review_queue": output_dir / "review_queue.json",
        "review_decisions": output_dir / "review_decisions.json",
        "kg_construction_diff": output_dir / "kg_construction_diff.json",
        "kg_overlay_validation_report": output_dir / "kg_overlay_validation_report.json",
        "source_units": output_dir / "source_units.jsonl",
        "knowledge_cards": output_dir / "knowledge_cards.jsonl",
        "entities": output_dir / "entities.jsonl",
        "validation_report": output_dir / "validation_report.json",
        "domain_profiles": output_dir / "domain_profiles.json",
        "domain_profile_report": output_dir / "domain_profile_report.json",
        "domain_profiles_manifest": output_dir / "domain_profiles" / "manifest.json",
        "runtime_views_manifest": output_dir / "runtime_views" / "manifest.json",
    }
    if "/" in artifact_key or "\\" in artifact_key or artifact_key not in artifacts:
        raise ValueError(f"unknown construction artifact key: {artifact_key}")
    resolved = artifacts[artifact_key]
    if not resolved.exists():
        raise ValueError(f"construction build artifact not found: {artifact_key}")
    if resolved.is_dir():
        raise ValueError(f"construction build artifact is a directory: {artifact_key}")
    return resolved


def validate_kg_construction_build(
    run_id: str,
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildValidationResponse:
    """Run structured KG QA for one construction build."""
    build = _find_build_record(run_id, build_root=build_root)
    report = run_kg_qa([build.nodes_path], [build.edges_path])
    return KGConstructionBuildValidationResponse(
        build=build,
        qa_report=report.model_dump(),
    )


def validate_kg_construction_overlay(
    run_id: str,
    request: KGConstructionOverlayValidationRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionOverlayValidationResponse:
    """Validate one candidate construction build as a runtime/import overlay."""
    build = _find_build_record(run_id, build_root=build_root)
    output_dir = Path(build.output_dir)
    result = run_kg_overlay_validation(
        KGOverlayValidationConfig(
            build_dir=output_dir,
            example_dir=Path(request.example_dir),
            include_defaults_for_runtime=not request.overlay_only_runtime,
            include_defaults_for_import=not request.overlay_only_import,
            top_k=request.top_k,
        )
    )
    return KGConstructionOverlayValidationResponse(
        build=build,
        report=result.report,
        report_path=(str(result.output_path) if result.output_path is not None else None),
    )


def publish_kg_construction_build(
    run_id: str,
    request: KGConstructionPublishRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionPublishResponse:
    """Dry-run or explicitly publish one construction build to Neo4j."""
    build = _find_build_record(run_id, build_root=build_root)
    _require_build_artifacts(build)
    if not request.dry_run and not request.confirm_publish:
        raise ValueError(
            "confirmed Neo4j publication requires confirm_publish=true when "
            "dry_run=false"
        )

    node_paths, edge_paths = _publish_paths(build, include_defaults=request.include_defaults)
    graph = KnowledgeGraph.from_paths(node_paths, edge_paths, skip_missing=True)
    if request.dry_run:
        summary = dry_run_import(graph)
    else:
        config = resolve_neo4j_config(
            uri=request.uri,
            user=request.user,
            password=request.password,
            database=request.database,
            config_path=request.config_path,
        )
        summary = import_knowledge_graph_with_config(graph, config)

    return KGConstructionPublishResponse(
        build=build,
        import_summary=KGConstructionImportSummary(
            node_count=summary.node_count,
            edge_count=summary.edge_count,
            dry_run=summary.dry_run,
        ),
        include_defaults=request.include_defaults,
        node_paths=[str(path) for path in node_paths],
        edge_paths=[str(path) for path in edge_paths],
    )


def review_kg_construction_edge(
    run_id: str,
    request: KGConstructionEdgeReviewRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionEdgeReviewResponse:
    """Record an accept/reject decision for one candidate construction edge."""
    build = _find_build_record(run_id, build_root=build_root)
    _require_build_artifacts(build)
    target_key = request.edge_key()
    edge_rows = _read_edge_rows(Path(build.edges_path))
    updated_edge = _review_edge_row(edge_rows, target_key=target_key, action=request.action)
    _write_edge_rows(Path(build.edges_path), edge_rows)

    manifest = _load_json_object(Path(build.manifest_path), object_name="construction manifest")
    summary = _load_json_object(Path(build.summary_path), object_name="construction summary")
    _refresh_review_summary(summary, edge_rows)
    _refresh_manifest_review_summary(manifest, summary)
    decision = review_decision_for_edge(
        target_id=target_key,
        target_key=target_key,
        action=request.action,
        reviewer=request.reviewer,
        note=request.note,
        proposed_payload=request.proposed_payload or updated_edge,
        metadata={
            "run_id": build.run_id,
            "edge": updated_edge,
            **request.metadata,
        },
    )
    manifest.setdefault("review_decisions", []).append(decision.model_dump(mode="json"))
    _write_json_object(Path(build.summary_path), summary)
    _write_json_object(Path(build.manifest_path), manifest)
    refreshed_build = _build_record_from_manifest_path(Path(build.manifest_path))
    return KGConstructionEdgeReviewResponse(
        build=refreshed_build,
        decision=decision,
        edge=updated_edge,
        summary=summary,
        manifest_path=build.manifest_path,
        edges_path=build.edges_path,
    )


def get_kg_construction_review_queue(
    run_id: str,
    request: KGConstructionReviewQueueRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionReviewQueueResponse:
    """Return a filtered, paginated review queue for construction edges."""
    build = _find_build_record(run_id, build_root=build_root)
    _require_build_artifacts(build)
    rows = [_queue_edge_from_row(row) for row in _read_edge_rows(Path(build.edges_path))]
    filtered_rows = [
        edge
        for edge in rows
        if _matches_review_queue_filters(edge, request)
    ]
    page = filtered_rows[request.offset : request.offset + request.limit]
    return KGConstructionReviewQueueResponse(
        build=build,
        filters=request,
        total_count=len(filtered_rows),
        returned_count=len(page),
        offset=request.offset,
        limit=request.limit,
        edges=page,
        summary=_review_queue_summary(filtered_rows),
    )


def _uses_source_kg_compiler(request: KGConstructionBuildRequest) -> bool:
    """Return whether a build request should route through source_kg_compiler."""
    return any(
        source.source_type == "document"
        or source.source_format in {"text", "markdown"}
        for source in request.sources
    )


def _run_kg_construction_compiler_build(
    request: KGConstructionBuildRequest,
    *,
    output_dir: Path,
) -> KGConstructionBuildResponse:
    """Run the source_kg_compiler while preserving current build registry semantics."""
    run_id = request.run_id or build_kg_construction_run_id()
    source_paths = _compiler_source_paths_from_inputs(request.sources, output_dir)
    default_scenario = request.sources[0].scenario if request.sources else "shared"
    compiler_result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=tuple(source_paths),
            output_dir=output_dir,
            llm_client=OpenAICompatibleSourceKGLLM(),
            default_scenario=default_scenario,
            overwrite=request.overwrite,
            llm_concurrency=request.llm_concurrency,
        )
    )
    edge_rows = _read_csv_rows(compiler_result.artifact_paths.edges_csv)
    summary_payload = _compiler_build_summary_payload(
        run_id=run_id,
        request=request,
        output_dir=output_dir,
        compiler_summary=compiler_result.summary,
        edge_rows=edge_rows,
    )
    manifest_payload = _compiler_build_manifest_payload(
        run_id=run_id,
        request=request,
        output_dir=output_dir,
        compiler_result=compiler_result,
        summary_payload=summary_payload,
    )
    summary_path = output_dir / "kg_construction_summary.json"
    manifest_path = output_dir / "kg_construction_manifest.json"
    _write_json_object(summary_path, summary_payload)
    _write_json_object(manifest_path, manifest_payload)
    return KGConstructionBuildResponse(
        status="built",
        run_id=run_id,
        output_dir=str(output_dir),
        nodes_path=str(compiler_result.artifact_paths.nodes_csv),
        edges_path=str(compiler_result.artifact_paths.edges_csv),
        summary_path=str(summary_path),
        manifest_path=str(manifest_path),
        source_units_path=str(compiler_result.artifact_paths.source_units),
        knowledge_cards_path=str(compiler_result.artifact_paths.knowledge_cards),
        entities_path=str(compiler_result.artifact_paths.entities),
        validation_report_path=str(compiler_result.artifact_paths.validation_report),
        domain_profiles_path=str(compiler_result.artifact_paths.domain_profiles),
        domain_profile_report_path=str(compiler_result.artifact_paths.domain_profile_report),
        domain_profiles_manifest_path=str(compiler_result.artifact_paths.domain_profiles_manifest),
        runtime_views_manifest_path=str(compiler_result.artifact_paths.runtime_views_manifest),
        summary=summary_payload,
    )


def _compiler_source_paths_from_inputs(
    sources: list[KGConstructionSourceInput],
    output_dir: Path,
) -> list[Path]:
    """Materialize inline compiler sources into files and return filesystem inputs."""
    inline_dir = output_dir.parent / "_compiler_inputs" / output_dir.name
    paths: list[Path] = []
    for source in sources:
        if source.path:
            paths.append(Path(source.path))
            continue
        if source.semantic_nodes_path and source.semantic_edges_path:
            paths.extend([Path(source.semantic_nodes_path), Path(source.semantic_edges_path)])
            continue
        inline_dir.mkdir(parents=True, exist_ok=True)
        suffix = _compiler_source_suffix(source.source_format)
        source_name = _safe_path_component(source.source_id, field_name="source_id")
        inline_path = inline_dir / f"{source_name}.{suffix}"
        inline_text = source.source_text or ""
        if source.source_type == "document":
            inline_path.write_text(inline_text, encoding="utf-8")
        else:
            inline_path.write_text(inline_text, encoding="utf-8")
        paths.append(inline_path)
    return paths


def _compiler_source_suffix(source_format: ConstructionSourceFormat | None) -> str:
    mapping = {
        "csv": "csv",
        "json": "json",
        "jsonl": "jsonl",
        "text": "txt",
        "markdown": "md",
    }
    return mapping.get(source_format or "text", "txt")


def _compiler_build_summary_payload(
    *,
    run_id: str,
    request: KGConstructionBuildRequest,
    output_dir: Path,
    compiler_summary: dict[str, Any],
    edge_rows: list[dict[str, str]],
) -> dict[str, Any]:
    counts = dict(compiler_summary.get("counts") or {})
    review_counts = Counter(row.get("review_status", "") for row in edge_rows)
    review_counts.pop("", None)
    scenario_counts = Counter(row.get("scenario", "") for row in edge_rows)
    scenario_counts.pop("", None)
    return {
        "artifact_type": "source_to_kg_construction_result_v1",
        "run_id": run_id,
        "source_count": len(request.sources),
        "source_ids": [source.source_id for source in request.sources],
        "draft_entity_count": int(counts.get("knowledge_cards") or 0),
        "draft_relation_count": int(counts.get("edges") or 0),
        "node_count": int(counts.get("entities") or 0),
        "edge_count": int(counts.get("edges") or 0),
        "node_labels": {},
        "edge_relations": {},
        "scenarios": dict(sorted(scenario_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "claim_boundary": (
            "source-to-KG outputs are candidate/reviewable KG rows; they are not "
            "published to Neo4j automatically"
        ),
        "output": {
            "output_dir": str(output_dir),
            "nodes": str(output_dir / "nodes.csv"),
            "edges": str(output_dir / "edges.csv"),
            "summary": str(output_dir / "kg_construction_summary.json"),
            "manifest": str(output_dir / "kg_construction_manifest.json"),
        },
        "compiler_summary": compiler_summary,
        "llm_concurrency": request.llm_concurrency,
    }


def _compiler_build_manifest_payload(
    *,
    run_id: str,
    request: KGConstructionBuildRequest,
    output_dir: Path,
    compiler_result,
    summary_payload: dict[str, Any],
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    return {
        "artifact_type": "source_to_kg_construction_manifest_v1",
        "run": {
            "run_id": run_id,
            "created_at": created_at,
            "status": "built",
            "source_ids": [source.source_id for source in request.sources],
            "scenario_counts": dict(summary_payload.get("scenarios") or {}),
            "metadata": {
                "builder": "source_kg_compiler",
                "llm_concurrency": request.llm_concurrency,
            },
        },
        "summary": dict(summary_payload),
        "sources": [source.model_dump(mode="json") for source in request.sources],
        "artifacts": {
            "output_dir": str(output_dir),
            "nodes": str(compiler_result.artifact_paths.nodes_csv),
            "edges": str(compiler_result.artifact_paths.edges_csv),
            "summary": str(output_dir / "kg_construction_summary.json"),
            "manifest": str(output_dir / "kg_construction_manifest.json"),
            "source_units": str(compiler_result.artifact_paths.source_units),
            "knowledge_cards": str(compiler_result.artifact_paths.knowledge_cards),
            "entities": str(compiler_result.artifact_paths.entities),
            "validation_report": str(compiler_result.artifact_paths.validation_report),
            "domain_profiles": str(compiler_result.artifact_paths.domain_profiles),
            "domain_profile_report": str(compiler_result.artifact_paths.domain_profile_report),
            "domain_profiles_manifest": str(
                compiler_result.artifact_paths.domain_profiles_manifest
            ),
            "runtime_views_manifest": str(compiler_result.artifact_paths.runtime_views_manifest),
        },
        "draft_rows": [],
        "review_decisions": [],
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


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


def _build_manifest_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.name == "kg_construction_manifest.json" else []
    return sorted(root.glob("*/kg_construction_manifest.json"))


def _find_build_record(
    run_id: str,
    *,
    build_root: Path | None,
) -> KGConstructionBuildRecord:
    requested = _safe_path_component(run_id, field_name="run_id")
    for build in list_kg_construction_builds(build_root=build_root).builds:
        if build.run_id == requested:
            return build
    raise ValueError(f"unknown construction build run_id: {run_id}")


def _build_record_from_manifest_path(manifest_path: Path) -> KGConstructionBuildRecord:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"construction manifest must be an object: {manifest_path}")
    if manifest.get("artifact_type") != "source_to_kg_construction_manifest_v1":
        raise ValueError(f"unsupported construction manifest: {manifest_path}")
    run = _dict_value(manifest, "run")
    summary = _dict_value(manifest, "summary")
    artifacts = _dict_value(manifest, "artifacts")
    run_id = str(run.get("run_id") or summary.get("run_id") or "")
    if not run_id:
        raise ValueError(f"construction manifest missing run_id: {manifest_path}")
    output_dir = artifacts.get("output_dir") or manifest_path.parent
    return KGConstructionBuildRecord(
        run_id=run_id,
        status=str(run.get("status") or "built"),
        created_at=_str_or_none(run.get("created_at")),
        output_dir=str(output_dir),
        nodes_path=str(artifacts.get("nodes") or manifest_path.parent / "nodes.csv"),
        edges_path=str(artifacts.get("edges") or manifest_path.parent / "edges.csv"),
        summary_path=str(
            artifacts.get("summary") or manifest_path.parent / "kg_construction_summary.json"
        ),
        manifest_path=str(artifacts.get("manifest") or manifest_path),
        source_ids=[str(item) for item in summary.get("source_ids", [])],
        source_count=_int_value(summary.get("source_count")),
        node_count=_int_value(summary.get("node_count")),
        edge_count=_int_value(summary.get("edge_count")),
        scenarios=_int_dict(summary.get("scenarios")),
        review_status_counts=_int_dict(summary.get("review_status_counts")),
    )


def _publish_paths(
    build: KGConstructionBuildRecord,
    *,
    include_defaults: bool,
) -> tuple[list[Path], list[Path]]:
    node_paths = [Path(build.nodes_path)]
    edge_paths = [Path(build.edges_path)]
    if include_defaults:
        node_paths = [*DEFAULT_NODE_PATHS, *node_paths]
        edge_paths = [*DEFAULT_EDGE_PATHS, *edge_paths]
    return node_paths, edge_paths


def _require_build_artifacts(build: KGConstructionBuildRecord) -> None:
    missing = [
        path
        for path in (Path(build.nodes_path), Path(build.edges_path))
        if not path.is_file()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise ValueError(f"construction build artifact not found: {joined}")


def _read_edge_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"construction build edges not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(EDGE_COLUMNS).difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"edge CSV missing required columns: {sorted(missing)}")
        return [{key: row.get(key, "") for key in EDGE_COLUMNS} for row in reader]


def _write_edge_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDGE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _review_edge_row(
    rows: list[dict[str, str]],
    *,
    target_key: str,
    action: Literal["accept", "reject"],
) -> dict[str, Any]:
    for row in rows:
        if _edge_key_from_row(row) != target_key:
            continue
        row["feedback_count"] = str(_int_value(row.get("feedback_count")) + 1)
        if action == "accept":
            row["review_status"] = "reviewed"
            row["accepted_count"] = str(_int_value(row.get("accepted_count")) + 1)
        elif action == "reject":
            row["review_status"] = "rejected"
            row["rejected_count"] = str(_int_value(row.get("rejected_count")) + 1)
        return dict(row)
    raise ValueError(f"unknown construction edge target_key: {target_key}")


def _edge_key_from_row(row: dict[str, str]) -> str:
    return _safe_edge_key(
        "|".join(
            (
                row.get("head", ""),
                row.get("relation", ""),
                row.get("tail", ""),
                row.get("scenario", ""),
            )
        )
    )


def _safe_edge_key(value: str) -> str:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 4 or any(not part for part in parts):
        raise ValueError("edge target_key must have form head|relation|tail|scenario")
    return "|".join(parts)


def _queue_edge_from_row(row: dict[str, str]) -> KGConstructionReviewQueueEdge:
    return KGConstructionReviewQueueEdge(
        target_key=_edge_key_from_row(row),
        head=row.get("head", ""),
        relation=row.get("relation", ""),
        tail=row.get("tail", ""),
        scenario=row.get("scenario", ""),
        source=row.get("source", ""),
        evidence=row.get("evidence", ""),
        confidence=_float_value(row.get("confidence")),
        weight=_float_value(row.get("weight")),
        review_status=row.get("review_status", ""),
        feedback_count=_int_value(row.get("feedback_count")),
        accepted_count=_int_value(row.get("accepted_count")),
        rejected_count=_int_value(row.get("rejected_count")),
    )


def _matches_review_queue_filters(
    edge: KGConstructionReviewQueueEdge,
    request: KGConstructionReviewQueueRequest,
) -> bool:
    if request.review_status and edge.review_status != request.review_status:
        return False
    if request.source and edge.source != request.source:
        return False
    if request.scenario and edge.scenario != request.scenario:
        return False
    if request.relation and edge.relation != request.relation:
        return False
    if request.query and _normalize_query(request.query) not in _normalize_query(
        " ".join(
            (
                edge.target_key,
                edge.head,
                edge.relation,
                edge.tail,
                edge.source,
                edge.evidence,
            )
        )
    ):
        return False
    return True


def _review_queue_summary(
    rows: list[KGConstructionReviewQueueEdge],
) -> KGConstructionReviewQueueSummary:
    return KGConstructionReviewQueueSummary(
        review_status_counts=_count_values(edge.review_status for edge in rows),
        relation_counts=_count_values(edge.relation for edge in rows),
        scenario_counts=_count_values(edge.scenario for edge in rows),
        source_counts=_count_values(edge.source for edge in rows),
    )


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts = Counter(str(value) for value in values if str(value))
    return dict(sorted(counts.items()))


def _normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _load_json_object(path: Path, *, object_name: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{object_name} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{object_name} must be a JSON object: {path}")
    return payload


def _write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _refresh_review_summary(
    summary: dict[str, Any],
    edge_rows: list[dict[str, str]],
) -> None:
    review_counts = Counter(row.get("review_status", "") for row in edge_rows)
    review_counts.pop("", None)
    summary["review_status_counts"] = dict(sorted(review_counts.items()))


def _refresh_manifest_review_summary(
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    manifest_summary = manifest.get("summary")
    if isinstance(manifest_summary, dict):
        manifest_summary["review_status_counts"] = summary.get("review_status_counts", {})
    run = manifest.get("run")
    if isinstance(run, dict) and summary.get("review_status_counts"):
        statuses = set(_int_dict(summary.get("review_status_counts")))
        if statuses and "auto" not in statuses:
            run["status"] = "reviewed"


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    raise ValueError(f"construction manifest missing object field: {key}")


def _int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int_value(item) for key, item in value.items()}


def _int_value(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


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
    "KGConstructionBuildDetail",
    "KGConstructionEdgeReviewRequest",
    "KGConstructionEdgeReviewResponse",
    "KGConstructionImportSummary",
    "KGConstructionBuildListResponse",
    "KGConstructionOverlayValidationRequest",
    "KGConstructionOverlayValidationResponse",
    "KGConstructionPublishRequest",
    "KGConstructionPublishResponse",
    "KGConstructionReviewQueueEdge",
    "KGConstructionReviewQueueRequest",
    "KGConstructionReviewQueueResponse",
    "KGConstructionReviewQueueSummary",
    "KGConstructionBuildRecord",
    "KGConstructionBuildValidationResponse",
    "KGConstructionSourceListResponse",
    "KGConstructionSourceInput",
    "KGConstructionSourceUploadRequest",
    "KGConstructionUploadedSource",
    "get_kg_construction_build",
    "get_kg_construction_build_artifact_path",
    "get_kg_construction_review_queue",
    "list_kg_construction_source_uploads",
    "list_kg_construction_builds",
    "publish_kg_construction_build",
    "review_kg_construction_edge",
    "run_kg_construction_build",
    "save_kg_construction_source_upload",
    "safe_output_name",
    "validate_kg_construction_build",
    "validate_kg_construction_overlay",
]


def safe_output_name(value: str) -> str:
    """Public alias for the construction output-name sanitizer."""
    return _safe_output_name(value)
