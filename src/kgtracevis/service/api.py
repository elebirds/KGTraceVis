"""FastAPI entry point for KGTraceVis API clients."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

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
    get_kg_construction_build,
    list_kg_construction_builds,
    list_kg_construction_source_uploads,
    run_kg_construction_build,
    save_kg_construction_source_upload,
    validate_kg_construction_build,
)
from kgtracevis.service.kg_drafts import KGDraftRequest, record_kg_draft
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


def create_app() -> FastAPI:
    """Create the FastAPI application used by dashboard/API clients."""
    app = FastAPI(
        title="KGTraceVis Web API",
        version="0.1.0",
        description=(
            "API for evidence inspection and candidate/plausible KG explanation paths."
        ),
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
            requested = request.models or ["mvtec-stfpm"]
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

    @app.post("/api/kg/construction/build")
    def kg_construction_build(request: KGConstructionBuildRequest) -> dict[str, object]:
        try:
            return run_kg_construction_build(request).model_dump(mode="json")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        tep_rca_provider: Annotated[str | None, Form()] = None,
        tep_rca_artifact_dir: Annotated[str | None, Form()] = None,
        tep_rca_ranking_path: Annotated[str | None, Form()] = None,
        tep_rca_contributions_path: Annotated[str | None, Form()] = None,
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
                tep_rca_provider=tep_rca_provider,
                tep_rca_artifact_dir=tep_rca_artifact_dir,
                tep_rca_ranking_path=tep_rca_ranking_path,
                tep_rca_contributions_path=tep_rca_contributions_path,
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
