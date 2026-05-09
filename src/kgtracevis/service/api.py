"""FastAPI entry point for the KGTraceVis web system."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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
from kgtracevis.service.runs import (
    create_run_from_upload,
    get_run_detail,
    list_runs,
    parse_dataset_override,
    parse_upload_mode,
)


def create_app() -> FastAPI:
    """Create the FastAPI application used by the React web client."""
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

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        try:
            return get_run_detail(run_id).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/runs/upload")
    async def upload_run(
        file: Annotated[UploadFile, File()],
        mode: Annotated[str, Form()] = "records",
        dataset: Annotated[str | None, Form()] = None,
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
                top_k=top_k,
            ).model_dump(mode="json")
        except ValueError as exc:
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
        return record_feedback(request)

    return app


app = create_app()
