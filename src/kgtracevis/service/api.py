"""FastAPI entry point for KGTraceVis API clients."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from kgtracevis.kg.import_neo4j import Neo4jImportError
from kgtracevis.producers.model_assets import MODEL_ASSET_CHOICES, ModelAsset
from kgtracevis.service.dashboard import dashboard_bootstrap
from kgtracevis.service.handlers import (
    AnalyzeRequest,
    FeedbackRequest,
    WhatIfRequest,
    analyze_request,
    get_case_detail,
    list_cases,
    record_feedback,
    what_if_request,
)
from kgtracevis.service.kg_construction import (
    ConstructionSourceFormat,
    ConstructionSourceType,
    KGConstructionBuildRequest,
    KGConstructionEdgeReviewRequest,
    KGConstructionOverlayValidationRequest,
    KGConstructionPublishRequest,
    KGConstructionReviewQueueRequest,
    get_kg_construction_build,
    get_kg_construction_build_artifact_path,
    get_kg_construction_build_job,
    get_kg_construction_review_queue,
    list_kg_construction_builds,
    list_kg_construction_source_uploads,
    publish_kg_construction_build,
    review_kg_construction_edge,
    run_kg_construction_build,
    save_kg_construction_source_upload,
    submit_kg_construction_build_job,
    validate_kg_construction_build,
    validate_kg_construction_overlay,
)
from kgtracevis.service.kg_drafts import KGDraftRequest, record_kg_draft
from kgtracevis.service.kg_material_build import run_kg_material_build
from kgtracevis.service.kg_materials import (
    KGMaterialDirectBuildRequest,
    KGMaterialExtractionRunRequest,
    KGMaterialRegisterRequest,
    KGMaterialSelectedBuildRequest,
    MaterialType,
    extract_kg_material_to_structured_records,
    get_kg_material,
    list_kg_materials,
    prepare_kg_material_construction_build,
    register_kg_material,
    save_kg_material_upload,
)
from kgtracevis.service.kg_runtime_edit import (
    RuntimeKGEdgeConfidenceRequest,
    RuntimeKGEdgeRequest,
    RuntimeKGNodeRequest,
    delete_runtime_kg_edge,
    delete_runtime_kg_node,
    update_runtime_kg_edge_confidence,
    upsert_runtime_kg_edge,
    upsert_runtime_kg_node,
)
from kgtracevis.service.kg_source_drafts import (
    KGSourceDraftRequest,
    generate_source_kg_draft,
)
from kgtracevis.service.kg_studio import kg_studio_payload
from kgtracevis.service.runs import (
    create_run_from_upload,
    download_model_assets,
    get_run_artifact_path,
    get_run_detail,
    list_runs,
    mvtec_model_presets,
    parse_dataset_override,
    parse_upload_mode,
)


class ModelAssetDownloadRequest(BaseModel):
    """Request body for downloading trusted public model assets."""

    model_config = ConfigDict(extra="forbid")

    models: list[str] | None = None
    force: bool = False


class KGMaterialRegisterUrlRequest(BaseModel):
    """Frontend-friendly request to register one remote source material URL."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    scenario: str = "shared"
    source_type: str = "webpage"
    notes: str | None = None
    metadata: dict[str, Any] | None = None
    material_id: str | None = None


def create_app() -> FastAPI:
    """Create the FastAPI application used by dashboard/API clients."""
    app = FastAPI(
        title="KGTraceVis Web API",
        version="0.1.0",
        description=("API for evidence inspection and candidate/plausible KG explanation paths."),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard/bootstrap")
    def dashboard_bootstrap_route() -> dict[str, object]:
        return dashboard_bootstrap().model_dump(mode="json")

    @app.get("/api/cases")
    def cases() -> list[dict[str, object]]:
        return [case.model_dump(mode="json") for case in list_cases()]

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, top_k: int = 5) -> dict[str, object]:
        try:
            return get_case_detail(case_id, top_k=top_k)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/runs")
    def runs() -> list[dict[str, object]]:
        return [run.model_dump(mode="json") for run in list_runs()]

    @app.get("/api/runs/mvtec-model-presets")
    def mvtec_presets() -> dict[str, object]:
        return {
            "default_preset": "auto",
            "presets": mvtec_model_presets(),
        }

    @app.post("/api/model-assets/download")
    def download_assets(request: ModelAssetDownloadRequest) -> dict[str, object]:
        try:
            requested = request.models or ["mvtec-patchcore"]
            invalid = sorted({model for model in requested if model not in MODEL_ASSET_CHOICES})
            if invalid:
                supported = ", ".join(MODEL_ASSET_CHOICES)
                raise ValueError(f"model asset must be one of: {supported}")
            models = cast(tuple[ModelAsset, ...], tuple(requested))
            return download_model_assets(models=models, force=request.force)
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        try:
            return get_run_detail(run_id).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/artifacts/{artifact_name}")
    def run_artifact(run_id: str, artifact_name: str) -> FileResponse:
        try:
            return FileResponse(get_run_artifact_path(run_id, artifact_name))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/kg/studio")
    def kg_studio() -> dict[str, object]:
        return kg_studio_payload().model_dump(mode="json")

    @app.post("/api/kg/drafts")
    def kg_draft(request: KGDraftRequest) -> dict[str, object]:
        return record_kg_draft(request)

    @app.post("/api/kg/source-draft")
    def kg_source_draft(request: KGSourceDraftRequest) -> dict[str, object]:
        return generate_source_kg_draft(request).model_dump(mode="json")

    @app.post("/api/kg/runtime/nodes")
    def kg_runtime_node_upsert(request: RuntimeKGNodeRequest) -> dict[str, object]:
        try:
            return upsert_runtime_kg_node(request).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/kg/runtime/nodes/{node_id}")
    def kg_runtime_node_delete(node_id: str) -> dict[str, object]:
        try:
            return delete_runtime_kg_node(node_id).model_dump(mode="json")
        except ValueError as exc:
            status_code = 404 if "unknown KG node" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/kg/runtime/edges")
    def kg_runtime_edge_upsert(request: RuntimeKGEdgeRequest) -> dict[str, object]:
        try:
            return upsert_runtime_kg_edge(request).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/kg/runtime/edges/{edge_id}/confidence")
    def kg_runtime_edge_confidence_update(
        edge_id: str,
        request: RuntimeKGEdgeConfidenceRequest,
    ) -> dict[str, object]:
        try:
            return update_runtime_kg_edge_confidence(edge_id, request).model_dump(
                mode="json"
            )
        except ValueError as exc:
            status_code = 404 if "unknown KG edge" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.delete("/api/kg/runtime/edges/{edge_id}")
    def kg_runtime_edge_delete(edge_id: str) -> dict[str, object]:
        try:
            return delete_runtime_kg_edge(edge_id).model_dump(mode="json")
        except ValueError as exc:
            status_code = 404 if "unknown KG edge" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/kg/materials")
    def kg_materials() -> dict[str, object]:
        try:
            response = list_kg_materials()
            materials = [_material_api_record(material) for material in response.materials]
            return {
                "status": "ok",
                "material_dir": response.material_root,
                "material_root": response.material_root,
                "count": len(materials),
                "materials": materials,
                "note": "registered source materials for source-grounded KG construction",
            }
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/kg/materials/{material_id}")
    def kg_material_detail(material_id: str) -> dict[str, object]:
        try:
            material = get_kg_material(material_id).material
            return {"status": "ok", "material": _material_api_record(material)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/kg/materials/upload")
    async def kg_material_upload(
        file: Annotated[UploadFile, File()],
        title: Annotated[str | None, Form()] = None,
        scenario: Annotated[str, Form()] = "shared",
        source_type: Annotated[str, Form()] = "other",
        notes: Annotated[str | None, Form()] = None,
        metadata: Annotated[str | None, Form()] = None,
        material_id: Annotated[str | None, Form()] = None,
        overwrite: Annotated[bool, Form()] = False,
    ) -> dict[str, object]:
        try:
            content = await file.read()
            parsed_metadata = _metadata_from_form(metadata)
            if notes:
                parsed_metadata["notes"] = notes
            record = save_kg_material_upload(
                material_id=material_id
                or _generated_material_id(title or file.filename or "material"),
                title=title or Path(file.filename or "material").stem,
                filename=file.filename or "material.txt",
                content=content,
                scenario=scenario,
                material_type=cast(
                    MaterialType,
                    _material_type_from_source_type(
                        source_type,
                        filename=file.filename or "",
                        content_type=file.content_type,
                    ),
                ),
                content_type=file.content_type,
                metadata=parsed_metadata,
                overwrite=overwrite,
            )
            return {
                "status": "uploaded",
                "material": _material_api_record(record),
                "note": record.claim_boundary,
            }
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/kg/materials/register-url")
    def kg_material_register_url(request: KGMaterialRegisterUrlRequest) -> dict[str, object]:
        try:
            metadata = dict(request.metadata or {})
            if request.notes:
                metadata["notes"] = request.notes
            record = register_kg_material(
                KGMaterialRegisterRequest(
                    material_id=request.material_id
                    or _generated_material_id(request.title or request.url),
                    title=request.title or request.url,
                    source_uri=request.url,
                    source_kind="url",
                    scenario=request.scenario,
                    material_type=cast(
                        MaterialType,
                        _material_type_from_source_type(request.source_type),
                    ),
                    metadata=metadata,
                )
            )
            return {
                "status": "registered",
                "material": _material_api_record(record),
                "note": record.claim_boundary,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/kg/materials/register")
    def kg_material_register(request: KGMaterialRegisterRequest) -> dict[str, object]:
        try:
            record = register_kg_material(request)
            return {
                "status": record.status,
                "material": _material_api_record(record),
                "note": record.claim_boundary,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/kg/materials/{material_id}/extract")
    def kg_material_extract(
        material_id: str,
        request: KGMaterialExtractionRunRequest | None = None,
    ) -> dict[str, object]:
        try:
            response = extract_kg_material_to_structured_records(
                material_id,
                request or KGMaterialExtractionRunRequest(),
            )
            payload = response.model_dump(mode="json")
            payload["material"] = _material_api_record(response.material)
            return payload
        except ImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            status_code = 404 if "unknown material_id" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/kg/materials/build-sources")
    def kg_material_build_sources(
        request: KGMaterialSelectedBuildRequest,
    ) -> dict[str, object]:
        try:
            response = prepare_kg_material_construction_build(request)
            return response.model_dump(mode="json")
        except ValueError as exc:
            status_code = 404 if "unknown material_id" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/kg/materials/build")
    def kg_material_build(request: KGMaterialDirectBuildRequest) -> dict[str, object]:
        try:
            return run_kg_material_build(request).model_dump(mode="json")
        except ImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            status_code = 404 if "unknown material_id" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/kg/construction/build")
    def kg_construction_build(request: KGConstructionBuildRequest) -> dict[str, object]:
        try:
            return run_kg_construction_build(request).model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/kg/construction/build-jobs")
    def kg_construction_build_job_submit(
        request: KGConstructionBuildRequest,
    ) -> dict[str, object]:
        try:
            return submit_kg_construction_build_job(request).model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/kg/construction/build-jobs/{job_id}")
    def kg_construction_build_job_status(
        job_id: str,
        after_sequence: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=0, le=500)] = 200,
    ) -> dict[str, object]:
        try:
            return get_kg_construction_build_job(
                job_id,
                after_sequence=after_sequence,
                limit=limit,
            ).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/kg/construction/builds")
    def kg_construction_builds() -> dict[str, object]:
        try:
            return list_kg_construction_builds().model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/kg/construction/builds/{run_id}")
    def kg_construction_build_detail(run_id: str) -> dict[str, object]:
        try:
            return get_kg_construction_build(run_id).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/kg/construction/builds/{run_id}/validate")
    def kg_construction_build_validate(run_id: str) -> dict[str, object]:
        try:
            return validate_kg_construction_build(run_id).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/kg/construction/builds/{run_id}/validate-overlay")
    def kg_construction_build_validate_overlay(
        run_id: str,
        request: KGConstructionOverlayValidationRequest | None = None,
    ) -> dict[str, object]:
        try:
            validation_request = request or KGConstructionOverlayValidationRequest()
            return validate_kg_construction_overlay(
                run_id,
                validation_request,
            ).model_dump(mode="json")
        except ValueError as exc:
            status_code = (
                404 if "unknown construction build run_id" in str(exc) else 400
            )
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/kg/construction/builds/{run_id}/artifacts/{artifact_key}")
    def kg_construction_build_artifact(
        run_id: str,
        artifact_key: str,
    ) -> FileResponse:
        try:
            return FileResponse(
                get_kg_construction_build_artifact_path(run_id, artifact_key)
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = (
                404
                if "unknown construction build run_id" in detail
                or "unknown construction artifact key" in detail
                or "construction build artifact not found" in detail
                or "construction build artifact is a directory" in detail
                else 400
            )
            raise HTTPException(status_code=status_code, detail=detail) from exc

    @app.post("/api/kg/construction/builds/{run_id}/publish")
    def kg_construction_build_publish(
        run_id: str,
        request: Annotated[
            KGConstructionPublishRequest | None,
            Body(),
        ] = None,
    ) -> dict[str, object]:
        try:
            publish_request = request or KGConstructionPublishRequest()
            return publish_kg_construction_build(
                run_id,
                publish_request,
            ).model_dump(mode="json")
        except Neo4jImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            status_code = 404 if "unknown construction build run_id" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/kg/construction/builds/{run_id}/review")
    def kg_construction_edge_review(
        run_id: str,
        request: KGConstructionEdgeReviewRequest,
    ) -> dict[str, object]:
        try:
            return review_kg_construction_edge(run_id, request).model_dump(mode="json")
        except ValueError as exc:
            status_code = (
                404
                if "unknown construction build run_id" in str(exc)
                or "unknown construction edge target_key" in str(exc)
                or "unknown construction review target_key" in str(exc)
                else 400
            )
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/kg/construction/builds/{run_id}/review-queue")
    def kg_construction_review_queue(
        run_id: str,
        review_status: Literal["auto", "reviewed", "rejected"] | None = None,
        source: str | None = None,
        scenario: str | None = None,
        relation: str | None = None,
        query: str | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> dict[str, object]:
        try:
            request = KGConstructionReviewQueueRequest(
                review_status=review_status,
                source=source,
                scenario=scenario,
                relation=relation,
                query=query,
                offset=offset,
                limit=limit,
            )
            return get_kg_construction_review_queue(
                run_id,
                request,
            ).model_dump(mode="json")
        except ValueError as exc:
            status_code = 404 if "unknown construction build run_id" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/kg/construction/sources")
    def kg_construction_sources() -> dict[str, object]:
        try:
            return list_kg_construction_source_uploads().model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/kg/construction/sources/upload")
    async def kg_construction_source_upload(
        file: Annotated[UploadFile, File()],
        source_id: Annotated[str, Form()],
        source_type: Annotated[str, Form()] = "manual_table",
        scenario: Annotated[str, Form()] = "shared",
        source_format: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        try:
            content = await file.read()
            return save_kg_construction_source_upload(
                source_id=source_id,
                source_type=cast(ConstructionSourceType, source_type),
                scenario=scenario,
                filename=file.filename or "source.csv",
                content=content,
                source_format=cast(ConstructionSourceFormat | None, source_format),
            ).model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/upload")
    async def upload_run(
        file: Annotated[UploadFile, File()],
        mode: Annotated[str, Form()] = "records",
        dataset: Annotated[str | None, Form()] = None,
        object_name: Annotated[str | None, Form()] = None,
        defect_type: Annotated[str | None, Form()] = None,
        model_preset: Annotated[str | None, Form()] = None,
        reasoning_profile_id: Annotated[str | None, Form()] = None,
        top_k: Annotated[int, Form()] = 5,
    ) -> dict[str, object]:
        try:
            upload_mode = parse_upload_mode(mode)
            dataset_override = parse_dataset_override(dataset)
            content = await file.read()
            return create_run_from_upload(
                file.filename or "upload",
                content,
                mode=upload_mode,
                dataset=dataset_override,
                object_name=object_name,
                defect_type=defect_type,
                model_preset=model_preset,
                reasoning_profile_id=(
                    str(reasoning_profile_id).strip() if reasoning_profile_id else None
                ),
                top_k=top_k,
            ).model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/analyze")
    def analyze(request: AnalyzeRequest) -> dict[str, object]:
        try:
            return analyze_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/what-if")
    def what_if(request: WhatIfRequest) -> dict[str, object]:
        try:
            return what_if_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/feedback")
    def feedback(request: FeedbackRequest) -> dict[str, object]:
        try:
            return record_feedback(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()


def _metadata_from_form(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("metadata must be a JSON object")
    return payload


def _generated_material_id(seed: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", seed.strip()).strip("._").lower()
    slug = slug[:40].strip("._") or "material"
    return f"{slug}_{uuid.uuid4().hex[:8]}"


def _material_type_from_source_type(
    source_type: str,
    *,
    filename: str = "",
    content_type: str | None = None,
) -> str:
    lowered = " ".join([source_type, filename, content_type or ""]).lower()
    if "pdf" in lowered:
        return "pdf"
    if "web" in lowered or lowered.startswith("url"):
        return "webpage"
    if "jsonl" in lowered:
        return "jsonl"
    if "json" in lowered:
        return "json"
    if "csv" in lowered:
        return "csv"
    if "markdown" in lowered or filename.lower().endswith(".md"):
        return "markdown"
    if "text" in lowered or filename.lower().endswith(".txt"):
        return "text"
    return "other"


def _material_api_record(material: Any) -> dict[str, object]:
    payload = material.model_dump(mode="json")
    extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        **payload,
        "source_type": payload.get("material_type"),
        "source_format": extraction.get("source_format"),
        "path": payload.get("source_uri") if payload.get("source_kind") != "url" else None,
        "url": payload.get("source_uri") if payload.get("source_kind") == "url" else None,
        "uri": payload.get("source_uri"),
        "filename": payload.get("original_filename"),
        "processing_status": payload.get("status"),
        "extraction_status": extraction.get("status"),
        "chunk_count": metadata.get("chunk_count"),
        "page_count": metadata.get("page_count"),
        "source_id": extraction.get("source_id"),
        "notes": metadata.get("notes"),
        "created_at": payload.get("registered_at"),
    }
