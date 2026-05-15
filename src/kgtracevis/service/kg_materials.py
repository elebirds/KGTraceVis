"""Service DTOs and handlers for source material library management."""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.kg_construction.document_extraction import (
    DocumentIEClient,
    OpenAICompatibleKGExtractionClient,
    extract_draft_kg_from_source_material,
)
from kgtracevis.kg_construction.draft import DraftEntity, DraftRelation, KGConstructionSource
from kgtracevis.service.kg_construction import (
    ConstructionSourceFormat,
    KGConstructionBuildRequest,
    KGConstructionSourceInput,
)

DEFAULT_SOURCE_KG_MATERIAL_DIR = Path("runs/source_kg_materials")
MAX_MATERIAL_UPLOAD_BYTES = 20_000_000

MaterialSourceKind = Literal["uploaded_file", "url", "local_path", "citation"]
MaterialType = Literal[
    "pdf",
    "webpage",
    "text",
    "markdown",
    "csv",
    "json",
    "jsonl",
    "other",
]
MaterialStatus = Literal["registered", "uploaded", "extracted", "failed"]
ExtractionStatus = Literal["not_started", "extracted", "failed"]


class KGMaterialExtractionState(BaseModel):
    """Structured extraction metadata attached to one source material."""

    model_config = ConfigDict(extra="forbid")

    status: ExtractionStatus = "not_started"
    structured_records_path: str | None = None
    source_format: ConstructionSourceFormat = "jsonl"
    source_id: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    extracted_at: str | None = None
    record_count: int | None = Field(default=None, ge=0)
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_extraction_shape(self) -> KGMaterialExtractionState:
        """Keep extracted-state metadata explicit and build-checkable."""
        if self.status == "extracted" and not self.structured_records_path:
            raise ValueError("extraction.status=extracted requires structured_records_path")
        if self.status != "failed" and self.error_message:
            raise ValueError("error_message is only valid when extraction.status=failed")
        return self


class KGMaterialUploadRequest(BaseModel):
    """Metadata for an uploaded material file."""

    model_config = ConfigDict(extra="forbid")

    material_id: str
    title: str
    scenario: str = "shared"
    material_type: MaterialType = "other"
    filename: str
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_upload_shape(self) -> KGMaterialUploadRequest:
        """Validate upload metadata before bytes are persisted."""
        _safe_path_component(self.material_id, field_name="material_id")
        _safe_upload_filename(self.filename)
        _require_non_empty(self.title, field_name="title")
        _require_non_empty(self.scenario, field_name="scenario")
        return self


class KGMaterialRegisterRequest(BaseModel):
    """Request to register a URL, local path, citation, or extracted material."""

    model_config = ConfigDict(extra="forbid")

    material_id: str
    title: str
    source_uri: str
    source_kind: MaterialSourceKind = "url"
    scenario: str = "shared"
    material_type: MaterialType = "other"
    metadata: dict[str, Any] = Field(default_factory=dict)
    extraction: KGMaterialExtractionState = Field(default_factory=KGMaterialExtractionState)

    @model_validator(mode="after")
    def validate_register_shape(self) -> KGMaterialRegisterRequest:
        """Reject ambiguous source references without touching the network."""
        _safe_path_component(self.material_id, field_name="material_id")
        _require_non_empty(self.title, field_name="title")
        _require_non_empty(self.scenario, field_name="scenario")
        _require_non_empty(self.source_uri, field_name="source_uri")
        is_url = _looks_like_url(self.source_uri)
        if self.source_kind == "url" and not is_url:
            raise ValueError(
                "source_kind=url requires source_uri to start with http:// or https://"
            )
        if self.source_kind != "url" and is_url:
            raise ValueError("remote URLs must use source_kind=url")
        if self.extraction.structured_records_path and _looks_like_url(
            self.extraction.structured_records_path
        ):
            raise ValueError("structured_records_path must be a local file path")
        return self


class KGMaterialRecord(BaseModel):
    """Persisted material-library record."""

    model_config = ConfigDict(extra="forbid")

    status: MaterialStatus
    material_id: str
    title: str
    scenario: str
    material_type: MaterialType
    source_kind: MaterialSourceKind
    source_uri: str
    metadata_path: str
    registered_at: str
    updated_at: str
    original_filename: str | None = None
    content_type: str | None = None
    size_bytes: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extraction: KGMaterialExtractionState = Field(default_factory=KGMaterialExtractionState)
    claim_boundary: str = (
        "source materials are provenance inputs for candidate KG construction; "
        "registration or upload does not verify industrial facts or publish KG rows"
    )

    @property
    def is_build_ready(self) -> bool:
        """Return whether this material has local structured records for construction."""
        return self.extraction.status == "extracted" and bool(
            self.extraction.structured_records_path
        )


class KGMaterialListResponse(BaseModel):
    """List response for stored material-library records."""

    model_config = ConfigDict(extra="forbid")

    material_root: str
    materials: list[KGMaterialRecord]


class KGMaterialDetailResponse(BaseModel):
    """Detail response for one material-library record."""

    model_config = ConfigDict(extra="forbid")

    material: KGMaterialRecord


class KGMaterialSelectedBuildRequest(BaseModel):
    """Request to convert selected material IDs into construction source inputs."""

    model_config = ConfigDict(extra="forbid")

    material_ids: list[str]
    output_name: str = "material_library"
    overwrite: bool = False
    run_id: str | None = None
    source_type: Literal["structured_records", "manual_table"] = "structured_records"

    @model_validator(mode="after")
    def validate_selection(self) -> KGMaterialSelectedBuildRequest:
        """Require a concrete, unambiguous material selection."""
        if not self.material_ids:
            raise ValueError("material_ids must contain at least one material_id")
        normalized = [
            _safe_path_component(material_id, field_name="material_id")
            for material_id in self.material_ids
        ]
        duplicates = sorted(
            {material_id for material_id in normalized if normalized.count(material_id) > 1}
        )
        if duplicates:
            raise ValueError(f"material_ids contains duplicates: {', '.join(duplicates)}")
        return self


class KGMaterialBuildSourcesResponse(BaseModel):
    """Build-ready construction source inputs derived from selected materials."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"] = "ready"
    material_root: str
    request: KGMaterialSelectedBuildRequest
    materials: list[KGMaterialRecord]
    sources: list[KGConstructionSourceInput]
    construction_request: KGConstructionBuildRequest
    claim_boundary: str = (
        "material-derived construction inputs remain candidate/reviewable sources; "
        "they do not run extraction, call an LLM, fetch remote content, or publish to Neo4j"
    )


class KGMaterialExtractionRunRequest(BaseModel):
    """Request to parse one material and run source-grounded candidate extraction."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai"] = "openai"
    max_chars: int = Field(default=2_000, ge=200, le=8_000)
    overlap_chars: int = Field(default=200, ge=0, le=2_000)
    source_format: ConstructionSourceFormat = "jsonl"
    overwrite: bool = False

    @model_validator(mode="after")
    def validate_chunking(self) -> KGMaterialExtractionRunRequest:
        """Keep chunking options valid before extraction starts."""
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        if self.source_format != "jsonl":
            raise ValueError("material extraction writes JSONL; source_format must be jsonl")
        return self


class KGMaterialExtractionRunResponse(BaseModel):
    """Response for one material extraction run."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["extracted"] = "extracted"
    material: KGMaterialRecord
    structured_records_path: str
    record_count: int
    claim_boundary: str = (
        "LLM/IE outputs are source-grounded candidate KG rows for review; they "
        "are not verified industrial facts"
    )


def save_kg_material_upload(
    *,
    material_id: str,
    title: str,
    filename: str,
    content: bytes,
    scenario: str = "shared",
    material_type: MaterialType = "other",
    content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    material_root: Path | None = None,
    overwrite: bool = False,
) -> KGMaterialRecord:
    """Persist an uploaded source material and return its registry record."""
    request = KGMaterialUploadRequest(
        material_id=material_id,
        title=title,
        scenario=scenario,
        material_type=material_type,
        filename=filename,
        content_type=content_type,
        metadata=metadata or {},
    )
    if not content:
        raise ValueError("uploaded material file cannot be empty")
    if len(content) > MAX_MATERIAL_UPLOAD_BYTES:
        raise ValueError(
            f"uploaded material file exceeds {MAX_MATERIAL_UPLOAD_BYTES} bytes: {len(content)}"
        )

    record_dir = _material_dir(request.material_id, material_root=material_root)
    metadata_path = record_dir / "metadata.json"
    if metadata_path.exists() and not overwrite:
        raise ValueError(
            f"material_id already exists; pass overwrite=true to replace: {material_id}"
        )

    record_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = _safe_upload_filename(request.filename)
    source_path = record_dir / stored_filename
    source_path.write_bytes(content)
    now = _utc_now()
    record = KGMaterialRecord(
        status="uploaded",
        material_id=request.material_id,
        title=request.title,
        scenario=request.scenario,
        material_type=request.material_type,
        source_kind="uploaded_file",
        source_uri=str(source_path),
        metadata_path=str(metadata_path),
        registered_at=now,
        updated_at=now,
        original_filename=request.filename,
        content_type=request.content_type,
        size_bytes=len(content),
        metadata=request.metadata,
    )
    _write_material_record(record)
    return record


def register_kg_material(
    request: KGMaterialRegisterRequest,
    *,
    material_root: Path | None = None,
    overwrite: bool = False,
) -> KGMaterialRecord:
    """Register a source material reference without fetching or extracting it."""
    record_dir = _material_dir(request.material_id, material_root=material_root)
    metadata_path = record_dir / "metadata.json"
    if metadata_path.exists() and not overwrite:
        raise ValueError(
            f"material_id already exists; pass overwrite=true to replace: {request.material_id}"
        )

    record_dir.mkdir(parents=True, exist_ok=True)
    now = _utc_now()
    status: MaterialStatus = (
        "extracted" if request.extraction.status == "extracted" else "registered"
    )
    record = KGMaterialRecord(
        status=status,
        material_id=request.material_id,
        title=request.title,
        scenario=request.scenario,
        material_type=request.material_type,
        source_kind=request.source_kind,
        source_uri=request.source_uri,
        metadata_path=str(metadata_path),
        registered_at=now,
        updated_at=now,
        metadata=request.metadata,
        extraction=request.extraction,
    )
    _write_material_record(record)
    return record


def list_kg_materials(
    *,
    material_root: Path | None = None,
) -> KGMaterialListResponse:
    """List persisted material-library records."""
    root = material_root or DEFAULT_SOURCE_KG_MATERIAL_DIR
    if not root.exists():
        return KGMaterialListResponse(material_root=str(root), materials=[])
    materials = [
        _load_material_record(metadata_path)
        for metadata_path in sorted(root.glob("*/metadata.json"))
    ]
    materials.sort(key=lambda item: item.updated_at, reverse=True)
    return KGMaterialListResponse(material_root=str(root), materials=materials)


def get_kg_material(
    material_id: str,
    *,
    material_root: Path | None = None,
) -> KGMaterialDetailResponse:
    """Return one persisted material-library record."""
    metadata_path = (
        _material_dir(
            _safe_path_component(material_id, field_name="material_id"),
            material_root=material_root,
        )
        / "metadata.json"
    )
    if not metadata_path.is_file():
        raise ValueError(f"unknown material_id: {material_id}")
    return KGMaterialDetailResponse(material=_load_material_record(metadata_path))


def prepare_kg_material_construction_build(
    request: KGMaterialSelectedBuildRequest,
    *,
    material_root: Path | None = None,
) -> KGMaterialBuildSourcesResponse:
    """Return construction source inputs for selected extracted materials."""
    materials = [
        get_kg_material(material_id, material_root=material_root).material
        for material_id in request.material_ids
    ]
    sources = [
        _construction_source_from_material(material, source_type=request.source_type)
        for material in materials
    ]
    construction_request = KGConstructionBuildRequest(
        sources=sources,
        output_name=request.output_name,
        overwrite=request.overwrite,
        run_id=request.run_id,
    )
    return KGMaterialBuildSourcesResponse(
        material_root=str(material_root or DEFAULT_SOURCE_KG_MATERIAL_DIR),
        request=request,
        materials=materials,
        sources=sources,
        construction_request=construction_request,
    )


def extract_kg_material_to_structured_records(
    material_id: str,
    request: KGMaterialExtractionRunRequest,
    *,
    client: DocumentIEClient | None = None,
    material_root: Path | None = None,
) -> KGMaterialExtractionRunResponse:
    """Extract one material into structured records consumable by construction."""
    detail = get_kg_material(material_id, material_root=material_root)
    material = detail.material
    record_dir = Path(material.metadata_path).parent
    records_path = record_dir / "structured_records.jsonl"
    if records_path.exists() and not request.overwrite:
        raise ValueError("structured_records.jsonl already exists; pass overwrite=true to replace")

    source_path, source_metadata = _local_source_for_extraction(material)
    source = KGConstructionSource(
        source_id=material.material_id,
        source_type=_document_source_type(material),
        scenario=material.scenario,
        path=source_path,
        metadata={
            "material_id": material.material_id,
            "material_title": material.title,
            "material_type": material.material_type,
            "content_type": material.content_type or "",
            **source_metadata,
        },
    )
    ie_client = client or OpenAICompatibleKGExtractionClient()
    draft = extract_draft_kg_from_source_material(
        source,
        ie_client,
        max_chars=request.max_chars,
        overlap_chars=request.overlap_chars,
    )
    records = _structured_records_from_draft(draft)
    if not records:
        raise ValueError(f"material_id={material.material_id} produced no candidate records")
    _write_jsonl(records_path, records)

    now = _utc_now()
    updated = material.model_copy(
        update={
            "status": "extracted",
            "updated_at": now,
            "extraction": KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_format=request.source_format,
                source_id=material.material_id,
                extractor_name="openai_document_ie",
                extractor_version="v1",
                extracted_at=now,
                record_count=len(records),
            ),
        }
    )
    _write_material_record(updated)
    return KGMaterialExtractionRunResponse(
        material=updated,
        structured_records_path=str(records_path),
        record_count=len(records),
    )


def _construction_source_from_material(
    material: KGMaterialRecord,
    *,
    source_type: Literal["structured_records", "manual_table"],
) -> KGConstructionSourceInput:
    extraction = material.extraction
    if extraction.status != "extracted":
        raise ValueError(
            f"material_id={material.material_id} is not build-ready; "
            f"extraction.status must be extracted"
        )
    if not extraction.structured_records_path:
        raise ValueError(
            f"material_id={material.material_id} is not build-ready; "
            "missing extraction.structured_records_path"
        )
    records_path = Path(extraction.structured_records_path)
    if not records_path.is_file():
        raise ValueError(
            f"material_id={material.material_id} structured records not found: {records_path}"
        )

    source_id = extraction.source_id or material.material_id
    metadata: dict[str, Any] = {
        "material_id": material.material_id,
        "material_title": material.title,
        "material_type": material.material_type,
        "material_source_kind": material.source_kind,
        "material_source_uri": material.source_uri,
        "material_metadata_path": material.metadata_path,
    }
    if extraction.extractor_name:
        metadata["extractor_name"] = extraction.extractor_name
    if extraction.extractor_version:
        metadata["extractor_version"] = extraction.extractor_version
    if extraction.record_count is not None:
        metadata["record_count"] = extraction.record_count
    return KGConstructionSourceInput(
        source_id=source_id,
        source_type=source_type,
        scenario=material.scenario,
        path=str(records_path),
        source_format=extraction.source_format,
        metadata=metadata,
    )


def _local_source_for_extraction(material: KGMaterialRecord) -> tuple[Path, dict[str, str]]:
    if material.source_kind == "url":
        return _fetch_material_url_snapshot(material)
    source_path = Path(material.source_uri)
    if not source_path.is_file():
        raise ValueError(f"material source path not found: {source_path}")
    return source_path, {}


def _fetch_material_url_snapshot(material: KGMaterialRecord) -> tuple[Path, dict[str, str]]:
    record_dir = Path(material.metadata_path).parent
    snapshot_path = record_dir / "web_snapshot.txt"
    request = urllib.request.Request(
        material.source_uri,
        headers={"User-Agent": "KGTraceVis/0.1 source material fetcher"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        content = response.read(MAX_MATERIAL_UPLOAD_BYTES + 1)
        content_type = response.headers.get("content-type", "")
    if len(content) > MAX_MATERIAL_UPLOAD_BYTES:
        raise ValueError(
            f"remote material exceeds {MAX_MATERIAL_UPLOAD_BYTES} bytes: {material.source_uri}"
        )
    snapshot_path.write_bytes(content)
    return snapshot_path, {"content_type": content_type, "fetched_url": material.source_uri}


def _document_source_type(material: KGMaterialRecord) -> str:
    if material.material_type == "pdf":
        return "pdf"
    if material.material_type == "webpage" or material.source_kind == "url":
        return "web_snapshot"
    if material.material_type == "markdown":
        return "markdown"
    return "plain_text"


def _structured_records_from_draft(draft: object) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entity in getattr(draft, "entities", ()):
        if isinstance(entity, DraftEntity):
            records.append(_entity_record(entity))
    for relation in getattr(draft, "relations", ()):
        if isinstance(relation, DraftRelation):
            records.append(_relation_record(relation))
    return records


def _entity_record(entity: DraftEntity) -> dict[str, Any]:
    return {
        "id": entity.entity_id_suggestion,
        "name": entity.name,
        "label": entity.label,
        "scenario": entity.scenario,
        "aliases": "|".join(entity.aliases),
        "description": entity.description,
        "source": entity.source_id,
        "evidence": entity.evidence or entity.evidence_span,
        "confidence": entity.confidence,
        "record_type": "entity",
        "draft_id": entity.draft_id,
        "metadata": dict(entity.metadata),
    }


def _relation_record(relation: DraftRelation) -> dict[str, Any]:
    return {
        "head": relation.head,
        "relation": relation.relation,
        "tail": relation.tail,
        "scenario": relation.scenario,
        "source": relation.source_id,
        "evidence": relation.evidence or relation.evidence_span,
        "confidence": relation.confidence,
        "record_type": "relation",
        "draft_id": relation.draft_id,
        "metadata": dict(relation.metadata),
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _material_dir(material_id: str, *, material_root: Path | None) -> Path:
    safe_id = _safe_path_component(material_id, field_name="material_id")
    return (material_root or DEFAULT_SOURCE_KG_MATERIAL_DIR) / safe_id


def _load_material_record(metadata_path: Path) -> KGMaterialRecord:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"material metadata must be a JSON object: {metadata_path}")
    return KGMaterialRecord.model_validate(payload)


def _write_material_record(record: KGMaterialRecord) -> None:
    metadata_path = Path(record.metadata_path)
    metadata_path.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _safe_path_component(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    if Path(stripped).name != stripped:
        raise ValueError(f"{field_name} must be a single path component")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stripped).strip("._")
    if safe != stripped or not safe:
        raise ValueError(f"{field_name} may contain only letters, numbers, '.', '_', and '-'")
    return safe


def _safe_upload_filename(filename: str) -> str:
    return _safe_path_component(Path(filename).name, field_name="filename")


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _looks_like_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "DEFAULT_SOURCE_KG_MATERIAL_DIR",
    "MAX_MATERIAL_UPLOAD_BYTES",
    "ExtractionStatus",
    "KGMaterialBuildSourcesResponse",
    "KGMaterialDetailResponse",
    "KGMaterialExtractionRunRequest",
    "KGMaterialExtractionRunResponse",
    "KGMaterialExtractionState",
    "KGMaterialListResponse",
    "KGMaterialRecord",
    "KGMaterialRegisterRequest",
    "KGMaterialSelectedBuildRequest",
    "KGMaterialUploadRequest",
    "MaterialSourceKind",
    "MaterialStatus",
    "MaterialType",
    "get_kg_material",
    "extract_kg_material_to_structured_records",
    "list_kg_materials",
    "prepare_kg_material_construction_build",
    "register_kg_material",
    "save_kg_material_upload",
]
