"""Compatibility service for source KG compiler builds.

This module keeps the web/API construction endpoints stable while routing build
work to the current KGBuilder-style source KG compiler. It intentionally does
not depend on the removed legacy ``kg_construction`` package.
"""

from __future__ import annotations

import csv
import json
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.source_kg_compiler import (
    OpenAICompatibleSourceKGLLM,
    SourceKGCompilerConfig,
    run_source_kg_compiler_workflow,
)

DEFAULT_SOURCE_KG_BUILD_DIR = Path("runs/source_kg_builds")

ConstructionSourceType = Literal[
    "structured_records",
    "manual_table",
    "document",
    "tep_semantic_lift",
    "tep_variable_mapping",
    "tep_rca_graph",
]
ConstructionSourceFormat = Literal["csv", "json", "jsonl", "text", "markdown"]

CLAIM_BOUNDARY = (
    "source KG compiler outputs are source-grounded candidate facts; they are "
    "not reviewed industrial ground truth or a Neo4j publication"
)


class KGConstructionSourceInput(BaseModel):
    """Frontend-compatible source input for one compiler build."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: ConstructionSourceType = "document"
    scenario: str = "shared"
    path: str | None = None
    source_text: str | None = None
    source_format: ConstructionSourceFormat | None = None
    semantic_nodes_path: str | None = None
    semantic_edges_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_shape(self) -> KGConstructionSourceInput:
        """Require a file path, inline source text, or TEP semantic file pair."""
        safe_output_name(self.source_id)
        if self.path:
            return self
        if self.source_text and self.source_text.strip():
            return self
        if self.semantic_nodes_path and self.semantic_edges_path:
            return self
        raise ValueError(
            "construction source requires path, source_text, or semantic node/edge paths"
        )


class KGConstructionBuildRequest(BaseModel):
    """Request body for one source KG compiler build."""

    model_config = ConfigDict(extra="forbid")

    sources: list[KGConstructionSourceInput]
    output_name: str = "source_kg"
    overwrite: bool = False
    run_id: str | None = None

    @model_validator(mode="after")
    def validate_build_shape(self) -> KGConstructionBuildRequest:
        """Require at least one source."""
        if not self.sources:
            raise ValueError("sources must contain at least one source")
        safe_output_name(self.output_name)
        return self


class KGConstructionPublishRequest(BaseModel):
    """Retained request DTO; source compiler builds are not published here."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    confirm: bool = False
    include_defaults: bool = True


class KGConstructionOverlayValidationRequest(BaseModel):
    """Retained request DTO for compatibility with the web client."""

    model_config = ConfigDict(extra="forbid")

    example_dir: str = "data/examples"
    overlay_only_runtime: bool = False
    overlay_only_import: bool = False
    top_k: int = Field(default=5, ge=1)


class KGConstructionEdgeReviewRequest(BaseModel):
    """Retained request DTO; compiler output review is read-only for now."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "reject"]
    item_type: str = "edge"
    target_key: str
    reviewer: str | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGConstructionReviewQueueRequest(BaseModel):
    """Filters for generated compiler edge inspection."""

    model_config = ConfigDict(extra="forbid")

    review_status: Literal["auto", "reviewed", "rejected"] | None = None
    source: str | None = None
    scenario: str | None = None
    relation: str | None = None
    query: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class KGConstructionBuildResponse(BaseModel):
    """Response envelope for one source KG compiler build."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["built"] = "built"
    run_id: str
    output_dir: str
    nodes_path: str
    edges_path: str
    summary_path: str
    manifest_path: str
    source_library_manifest_path: str | None = None
    draft_manifest_path: str | None = None
    profile_manifest_path: str | None = None
    alignment_manifest_path: str | None = None
    source_audit_graph_manifest_path: str | None = None
    semantic_layer_manifest_path: str | None = None
    rca_view_manifest_path: str | None = None
    review_queue_path: str | None = None
    document_understanding_manifest_path: str | None = None
    document_map_path: str | None = None
    chunk_prompt_context_path: str | None = None
    cross_chunk_proposals_path: str | None = None
    publish_manifest_path: str | None = None
    publish_report_path: str | None = None
    diff_path: str | None = None
    published_nodes_path: str | None = None
    published_edges_path: str | None = None
    summary: dict[str, Any]
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionBuildRecord(BaseModel):
    """Registry record for one source KG compiler build."""

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
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionBuildListResponse(BaseModel):
    """List response for compiler build registry."""

    model_config = ConfigDict(extra="forbid")

    build_root: str
    builds: list[KGConstructionBuildRecord]


class KGConstructionBuildDetail(BaseModel):
    """Detail response for a compiler build."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    summary: dict[str, Any]
    manifest: dict[str, Any]


class KGConstructionBuildValidationResponse(BaseModel):
    """Validation response for a compiler build."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    report: dict[str, Any]
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionOverlayValidationResponse(BaseModel):
    """Runtime overlay validation compatibility response."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    report: dict[str, Any]
    report_path: str | None = None
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionImportSummary(BaseModel):
    """Compatibility summary for unsupported publish calls."""

    model_config = ConfigDict(extra="forbid")

    status: str
    dry_run: bool = True
    node_count: int = 0
    edge_count: int = 0


class KGConstructionPublishResponse(BaseModel):
    """Compatibility response for source compiler publish requests."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    import_summary: KGConstructionImportSummary
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionReviewQueueEdge(BaseModel):
    """Read-only generated edge review row."""

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
    feedback_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    item_type: str = "edge"
    priority: int | None = None
    reason: str = "generated by source_kg_compiler"
    relation_family: str = "SOURCE_COMPILER"
    graph_impact: str = "candidate_runtime_overlay"
    recommended_action: str = "inspect generated source evidence before use"
    candidate_payload: dict[str, Any] = Field(default_factory=dict)


class KGConstructionReviewQueueSummary(BaseModel):
    """Aggregate counts for generated compiler edges."""

    model_config = ConfigDict(extra="forbid")

    review_status_counts: dict[str, int]
    relation_counts: dict[str, int]
    scenario_counts: dict[str, int]
    source_counts: dict[str, int]


class KGConstructionReviewQueueResponse(BaseModel):
    """Read-only review queue for generated compiler edges."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    filters: dict[str, Any]
    total_count: int
    returned_count: int
    offset: int
    limit: int
    edges: list[KGConstructionReviewQueueEdge]
    summary: KGConstructionReviewQueueSummary
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionEdgeReviewResponse(BaseModel):
    """Compatibility response for unsupported generated-edge mutation."""

    model_config = ConfigDict(extra="forbid")

    build: KGConstructionBuildRecord
    decision: dict[str, Any]
    edge: dict[str, Any]
    item: dict[str, Any]
    summary: dict[str, Any]
    manifest_path: str
    edges_path: str
    claim_boundary: str = CLAIM_BOUNDARY


class KGConstructionSourceUploadRequest(BaseModel):
    """Metadata for uploading a compiler source file."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: ConstructionSourceType = "document"
    scenario: str = "shared"
    source_format: ConstructionSourceFormat | None = None


class KGConstructionUploadedSource(BaseModel):
    """Stored uploaded source descriptor."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: ConstructionSourceType
    scenario: str
    source_format: ConstructionSourceFormat | None = None
    path: str
    uploaded_at: str
    build_source: KGConstructionSourceInput


class KGConstructionSourceListResponse(BaseModel):
    """List response for uploaded compiler sources."""

    model_config = ConfigDict(extra="forbid")

    source_root: str
    sources: list[KGConstructionUploadedSource]


def run_kg_construction_build(
    request: KGConstructionBuildRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildResponse:
    """Compile provided sources with the current source KG compiler."""
    output_dir = (build_root or DEFAULT_SOURCE_KG_BUILD_DIR) / safe_output_name(
        request.output_name
    )
    run_id = request.run_id or f"sourcekg_{uuid.uuid4().hex[:12]}"
    source_paths = _materialize_source_inputs(request.sources, output_dir)
    default_scenario = _default_scenario(request.sources)
    result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=tuple(source_paths),
            output_dir=output_dir,
            llm_client=OpenAICompatibleSourceKGLLM(),
            default_scenario=default_scenario,
            overwrite=request.overwrite,
        )
    )
    summary = _build_summary(
        run_id=run_id,
        output_dir=output_dir,
        request=request,
        compiler_summary=result.summary,
    )
    summary_path = output_dir / "source_kg_build_summary.json"
    manifest_path = output_dir / "source_kg_build_manifest.json"
    _write_json(summary_path, summary)
    _write_json(
        manifest_path,
        {
            "artifact_type": "source_kg_compiler_build_manifest_v1",
            "run_id": run_id,
            "created_at": summary["created_at"],
            "source_ids": [source.source_id for source in request.sources],
            "compiler_artifacts": result.summary["artifacts"],
            "summary_path": summary_path.as_posix(),
            "claim_boundary": CLAIM_BOUNDARY,
        },
    )
    return KGConstructionBuildResponse(
        run_id=run_id,
        output_dir=output_dir.as_posix(),
        nodes_path=result.artifact_paths.nodes_csv.as_posix(),
        edges_path=result.artifact_paths.edges_csv.as_posix(),
        summary_path=summary_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        source_library_manifest_path=result.artifact_paths.source_units.as_posix(),
        draft_manifest_path=result.artifact_paths.knowledge_cards.as_posix(),
        profile_manifest_path=result.artifact_paths.domain_profiles_manifest.as_posix(),
        rca_view_manifest_path=result.artifact_paths.runtime_views_manifest.as_posix(),
        summary=summary,
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
    """Store an uploaded compiler source and return a build-ready descriptor."""
    if not content:
        raise ValueError("uploaded construction source cannot be empty")
    root = source_root or DEFAULT_SOURCE_KG_BUILD_DIR / "uploaded_sources"
    source_dir = root / safe_output_name(source_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    stored_name = _safe_filename(filename)
    path = source_dir / stored_name
    path.write_bytes(content)
    payload = KGConstructionUploadedSource(
        source_id=source_id,
        source_type=source_type,
        scenario=scenario,
        source_format=source_format,
        path=path.as_posix(),
        uploaded_at=_utc_now(),
        build_source=KGConstructionSourceInput(
            source_id=source_id,
            source_type=source_type,
            scenario=scenario,
            path=path.as_posix(),
            source_format=source_format,
        ),
    )
    _write_json(source_dir / "metadata.json", payload.model_dump(mode="json"))
    return payload


def list_kg_construction_source_uploads(
    *,
    source_root: Path | None = None,
) -> KGConstructionSourceListResponse:
    """List uploaded compiler sources."""
    root = source_root or DEFAULT_SOURCE_KG_BUILD_DIR / "uploaded_sources"
    sources = [
        KGConstructionUploadedSource.model_validate(json.loads(path.read_text()))
        for path in sorted(root.glob("*/metadata.json"))
    ] if root.exists() else []
    return KGConstructionSourceListResponse(source_root=root.as_posix(), sources=sources)


def list_kg_construction_builds(
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildListResponse:
    """List source compiler builds."""
    root = build_root or DEFAULT_SOURCE_KG_BUILD_DIR
    builds = [
        _build_record_from_dir(path.parent)
        for path in sorted(root.glob("*/source_kg_build_manifest.json"))
    ] if root.exists() else []
    builds.sort(key=lambda build: build.created_at or "", reverse=True)
    return KGConstructionBuildListResponse(build_root=root.as_posix(), builds=builds)


def get_kg_construction_build(
    run_id: str,
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildDetail:
    """Return one source compiler build detail."""
    build = _find_build(run_id, build_root=build_root)
    summary = _read_json(Path(build.summary_path))
    manifest = _read_json(Path(build.manifest_path))
    return KGConstructionBuildDetail(build=build, summary=summary, manifest=manifest)


def get_kg_construction_build_artifact_path(
    run_id: str,
    artifact_key: str,
    *,
    build_root: Path | None = None,
) -> Path:
    """Resolve a stable artifact key for one compiler build."""
    build = _find_build(run_id, build_root=build_root)
    output_dir = Path(build.output_dir)
    artifacts = {
        "nodes": Path(build.nodes_path),
        "edges": Path(build.edges_path),
        "summary": Path(build.summary_path),
        "manifest": Path(build.manifest_path),
        "source_units": output_dir / "source_units.jsonl",
        "knowledge_cards": output_dir / "knowledge_cards.jsonl",
        "entities": output_dir / "entities.jsonl",
        "qa_report": output_dir / "qa_report.json",
        "validation_report": output_dir / "validation_report.json",
        "domain_profiles": output_dir / "domain_profiles.json",
    }
    if "/" in artifact_key or "\\" in artifact_key or artifact_key not in artifacts:
        raise ValueError(f"unknown construction artifact key: {artifact_key}")
    path = artifacts[artifact_key]
    if not path.is_file():
        raise ValueError(f"construction build artifact not found: {artifact_key}")
    return path


def validate_kg_construction_build(
    run_id: str,
    *,
    build_root: Path | None = None,
) -> KGConstructionBuildValidationResponse:
    """Return the compiler validation report for one build."""
    build = _find_build(run_id, build_root=build_root)
    report_path = Path(build.output_dir) / "validation_report.json"
    return KGConstructionBuildValidationResponse(
        build=build,
        report=_read_json(report_path) if report_path.is_file() else {},
    )


def validate_kg_construction_overlay(
    run_id: str,
    request: KGConstructionOverlayValidationRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionOverlayValidationResponse:
    """Return a lightweight overlay validation report for generated CSVs."""
    build = _find_build(run_id, build_root=build_root)
    report = {
        "artifact_type": "source_kg_compiler_overlay_validation_v1",
        "validated": Path(build.nodes_path).is_file() and Path(build.edges_path).is_file(),
        "overlay_contributed": None,
        "node_count": build.node_count,
        "edge_count": build.edge_count,
        "request": request.model_dump(mode="json"),
        "note": "full runtime contribution validation is handled by source KG evaluation scripts",
    }
    report_path = Path(build.output_dir) / "kg_overlay_validation_report.json"
    _write_json(report_path, report)
    return KGConstructionOverlayValidationResponse(
        build=build,
        report=report,
        report_path=report_path.as_posix(),
    )


def publish_kg_construction_build(
    run_id: str,
    request: KGConstructionPublishRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionPublishResponse:
    """Return an explicit no-publish response for source compiler builds."""
    build = _find_build(run_id, build_root=build_root)
    return KGConstructionPublishResponse(
        build=build,
        import_summary=KGConstructionImportSummary(
            status="not_supported_source_compiler_build",
            dry_run=True,
            node_count=build.node_count,
            edge_count=build.edge_count,
        ),
    )


def review_kg_construction_edge(
    run_id: str,
    request: KGConstructionEdgeReviewRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionEdgeReviewResponse:
    """Reject mutation of generated compiler edges through the legacy endpoint."""
    build = _find_build(run_id, build_root=build_root)
    raise ValueError(
        "source KG compiler builds are read-only here; regenerate sources or use "
        f"material/compiler review workflows later. target_key={request.target_key}; "
        f"build={build.run_id}"
    )


def get_kg_construction_review_queue(
    run_id: str,
    request: KGConstructionReviewQueueRequest,
    *,
    build_root: Path | None = None,
) -> KGConstructionReviewQueueResponse:
    """Expose generated edges as a read-only inspection queue."""
    build = _find_build(run_id, build_root=build_root)
    edges = [_queue_edge_from_row(index, row) for index, row in enumerate(_read_edges(build))]
    edges = _filter_edges(edges, request)
    sliced = edges[request.offset : request.offset + request.limit]
    return KGConstructionReviewQueueResponse(
        build=build,
        filters=request.model_dump(mode="json"),
        total_count=len(edges),
        returned_count=len(sliced),
        offset=request.offset,
        limit=request.limit,
        edges=sliced,
        summary=_queue_summary(edges),
    )


def safe_output_name(value: str) -> str:
    """Return a safe filesystem slug."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    if not slug:
        raise ValueError("output/source name cannot be empty")
    return slug


def _default_scenario(sources: list[KGConstructionSourceInput]) -> str:
    scenarios = [source.scenario for source in sources if source.scenario]
    return scenarios[0] if scenarios else "shared"


def _materialize_source_inputs(
    sources: list[KGConstructionSourceInput],
    output_dir: Path,
) -> list[Path]:
    source_paths: list[Path] = []
    inline_dir = output_dir.parent / "_compiler_inputs" / output_dir.name
    for source in sources:
        if source.path:
            source_paths.append(Path(source.path).expanduser())
            continue
        if source.semantic_nodes_path and source.semantic_edges_path:
            source_paths.extend(
                [
                    Path(source.semantic_nodes_path).expanduser(),
                    Path(source.semantic_edges_path).expanduser(),
                ]
            )
            continue
        inline_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.source_format or "txt"
        inline_path = inline_dir / f"{safe_output_name(source.source_id)}.{suffix}"
        inline_path.write_text(
            f"SCENARIO: {source.scenario}\nSOURCE_ID: {source.source_id}\n\n"
            f"{source.source_text or ''}",
            encoding="utf-8",
        )
        source_paths.append(inline_path)
    return source_paths


def _build_summary(
    *,
    run_id: str,
    output_dir: Path,
    request: KGConstructionBuildRequest,
    compiler_summary: dict[str, Any],
) -> dict[str, Any]:
    counts = dict(compiler_summary.get("counts") or {})
    return {
        "artifact_type": "source_kg_compiler_build_summary_v1",
        "run_id": run_id,
        "status": "built",
        "created_at": _utc_now(),
        "output_dir": output_dir.as_posix(),
        "source_count": len(request.sources),
        "source_ids": [source.source_id for source in request.sources],
        "node_count": int(counts.get("entities") or 0),
        "edge_count": int(counts.get("edges") or 0),
        "counts": {
            **counts,
            "node_count": int(counts.get("entities") or 0),
            "edge_count": int(counts.get("edges") or 0),
            "source_count": len(request.sources),
        },
        "compiler_summary": compiler_summary,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _build_record_from_dir(output_dir: Path) -> KGConstructionBuildRecord:
    summary_path = output_dir / "source_kg_build_summary.json"
    manifest_path = output_dir / "source_kg_build_manifest.json"
    summary = _read_json(summary_path)
    edges = _edge_rows(output_dir / "edges.csv")
    scenarios = Counter(row.get("scenario", "unknown") for row in edges)
    statuses = Counter(row.get("review_status", "unknown") for row in edges)
    return KGConstructionBuildRecord(
        run_id=str(summary["run_id"]),
        status=str(summary.get("status") or "built"),
        created_at=summary.get("created_at"),
        output_dir=output_dir.as_posix(),
        nodes_path=(output_dir / "nodes.csv").as_posix(),
        edges_path=(output_dir / "edges.csv").as_posix(),
        summary_path=summary_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        source_ids=list(summary.get("source_ids") or []),
        source_count=int(summary.get("source_count") or 0),
        node_count=int(summary.get("node_count") or 0),
        edge_count=int(summary.get("edge_count") or len(edges)),
        scenarios=dict(scenarios),
        review_status_counts=dict(statuses),
    )


def _find_build(run_id: str, *, build_root: Path | None = None) -> KGConstructionBuildRecord:
    for build in list_kg_construction_builds(build_root=build_root).builds:
        if build.run_id == run_id:
            return build
    raise ValueError(f"unknown construction build run_id: {run_id}")


def _read_edges(build: KGConstructionBuildRecord) -> list[dict[str, str]]:
    return _edge_rows(Path(build.edges_path))


def _edge_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _queue_edge_from_row(index: int, row: dict[str, str]) -> KGConstructionReviewQueueEdge:
    target_key = f"{row.get('head')}|{row.get('relation')}|{row.get('tail')}|{index}"
    return KGConstructionReviewQueueEdge(
        target_key=target_key,
        head=row.get("head", ""),
        relation=row.get("relation", ""),
        tail=row.get("tail", ""),
        scenario=row.get("scenario", ""),
        source=row.get("source", ""),
        evidence=row.get("evidence", ""),
        confidence=float(row.get("confidence") or 0.0),
        weight=float(row.get("weight") or 0.0),
        review_status=row.get("review_status", "auto"),
        feedback_count=int(row.get("feedback_count") or 0),
        accepted_count=int(row.get("accepted_count") or 0),
        rejected_count=int(row.get("rejected_count") or 0),
        candidate_payload=row,
    )


def _filter_edges(
    edges: list[KGConstructionReviewQueueEdge],
    request: KGConstructionReviewQueueRequest,
) -> list[KGConstructionReviewQueueEdge]:
    query = (request.query or "").strip().lower()
    filtered: list[KGConstructionReviewQueueEdge] = []
    for edge in edges:
        if request.review_status and edge.review_status != request.review_status:
            continue
        if request.source and edge.source != request.source:
            continue
        if request.scenario and edge.scenario != request.scenario:
            continue
        if request.relation and edge.relation != request.relation:
            continue
        haystack = " ".join([edge.head, edge.relation, edge.tail, edge.evidence]).lower()
        if query and query not in haystack:
            continue
        filtered.append(edge)
    return filtered


def _queue_summary(edges: list[KGConstructionReviewQueueEdge]) -> KGConstructionReviewQueueSummary:
    return KGConstructionReviewQueueSummary(
        review_status_counts=dict(Counter(edge.review_status for edge in edges)),
        relation_counts=dict(Counter(edge.relation for edge in edges)),
        scenario_counts=dict(Counter(edge.scenario for edge in edges)),
        source_counts=dict(Counter(edge.source for edge in edges)),
    )


def _safe_filename(value: str) -> str:
    name = Path(value).name
    if not name or name in {".", ".."}:
        raise ValueError("invalid upload filename")
    return name


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "ConstructionSourceFormat",
    "ConstructionSourceType",
    "KGConstructionBuildDetail",
    "KGConstructionBuildListResponse",
    "KGConstructionBuildRecord",
    "KGConstructionBuildRequest",
    "KGConstructionBuildResponse",
    "KGConstructionBuildValidationResponse",
    "KGConstructionEdgeReviewRequest",
    "KGConstructionEdgeReviewResponse",
    "KGConstructionImportSummary",
    "KGConstructionOverlayValidationRequest",
    "KGConstructionOverlayValidationResponse",
    "KGConstructionPublishRequest",
    "KGConstructionPublishResponse",
    "KGConstructionReviewQueueEdge",
    "KGConstructionReviewQueueRequest",
    "KGConstructionReviewQueueResponse",
    "KGConstructionReviewQueueSummary",
    "KGConstructionSourceInput",
    "KGConstructionSourceListResponse",
    "KGConstructionSourceUploadRequest",
    "KGConstructionUploadedSource",
    "get_kg_construction_build",
    "get_kg_construction_build_artifact_path",
    "get_kg_construction_review_queue",
    "list_kg_construction_builds",
    "list_kg_construction_source_uploads",
    "publish_kg_construction_build",
    "review_kg_construction_edge",
    "run_kg_construction_build",
    "safe_output_name",
    "save_kg_construction_source_upload",
    "validate_kg_construction_build",
    "validate_kg_construction_overlay",
]
