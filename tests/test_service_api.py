"""Tests for the KGTraceVis FastAPI web service."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from kgtracevis.service import api as service_api
from kgtracevis.service import runs as service_runs
from kgtracevis.service.api import app
from kgtracevis.service.handlers import (
    FeedbackRequest,
    WhatIfRequest,
    get_case_detail,
    list_cases,
    record_feedback,
    what_if_request,
)


def test_case_index_includes_checked_in_and_real_output_cases() -> None:
    """The web case index should expose both example and real pipeline evidence."""
    cases = list_cases()
    case_ids = {case.case_id for case in cases}

    assert "mvtec_0001" in case_ids
    assert "wafer_0001" in case_ids
    assert "mvtec_capsule_test_crack_000" in case_ids
    assert "wm811k_row_100402" in case_ids


def test_case_detail_returns_analysis_for_real_outputs() -> None:
    """Detail loading should attach a fresh KG analysis envelope."""
    detail = get_case_detail("wm811k_row_100402", top_k=3)

    assert detail["case"]["case_id"] == "wm811k_row_100402"
    assert detail["analysis"]["case_id"] == "wm811k_row_100402"
    assert detail["analysis"]["top_k_paths"]
    assert detail["workflow_steps"]
    assert detail["workflow_steps"][0]["title"] == "Load evidence case"
    assert detail["claim_boundary"].startswith("candidate/plausible explanation")


def test_upload_run_route_persists_a_run_manifest(tmp_path: Path, monkeypatch) -> None:
    """Uploaded sample bundles should create reusable run-session artifacts."""
    original = service_api.create_run_from_upload
    original_list_runs = service_api.list_runs
    original_get_run_detail = service_api.get_run_detail

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original(*args, **kwargs)

    def _patched_list_runs(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original_list_runs(*args, **kwargs)

    def _patched_get_run_detail(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original_get_run_detail(*args, **kwargs)

    monkeypatch.setattr(service_api, "create_run_from_upload", _patched_create_run_from_upload)
    monkeypatch.setattr(service_api, "list_runs", _patched_list_runs)
    monkeypatch.setattr(service_api, "get_run_detail", _patched_get_run_detail)

    client = TestClient(app)
    with Path("data/examples/records/mvtec_records.jsonl").open("rb") as handle:
        response = client.post(
            "/api/runs/upload",
            files={"file": ("mvtec_records.jsonl", handle, "application/jsonl")},
            data={"mode": "records", "top_k": "2"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["mode"] == "records"
    assert payload["run"]["case_count"] == 2
    assert payload["workflow_steps"]
    assert payload["summary"]["case_count"] == 2

    run_id = payload["run"]["run_id"]
    manifest_path = tmp_path / "web_sessions" / run_id / "manifest.json"
    assert manifest_path.is_file()

    runs = client.get("/api/runs")
    run_detail = client.get(f"/api/runs/{run_id}")
    assert runs.status_code == 200
    assert any(item["run_id"] == run_id for item in runs.json())
    assert run_detail.status_code == 200
    assert run_detail.json()["run"]["run_id"] == run_id


def test_image_upload_mode_defaults_to_unknown_label_when_unspecified(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Raw image uploads should not require an operator defect label."""
    original = service_api.create_run_from_upload

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original(*args, **kwargs)

    monkeypatch.setattr(service_api, "create_run_from_upload", _patched_create_run_from_upload)
    client = TestClient(app)
    with Path("runs/real_model_pipeline/assets/mvtec/input_root/capsule/test/crack/000.png").open(
        "rb"
    ) as handle:
        response = client.post(
            "/api/runs/upload",
            files={"file": ("000.png", handle, "image/png")},
            data={
                "mode": "image",
                "dataset": "mvtec",
                "object_name": "capsule",
                "top_k": "2",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["mode"] == "image"
    assert payload["evidence"]["anomaly_type"] == "unknown"
    assert payload["evidence"]["morphology"] is None


def test_image_upload_mode_runs_mvtec_producer_path(tmp_path: Path, monkeypatch) -> None:
    """Image uploads should run the real MVTec record path before KG analysis."""

    class FakeMVTecBackend:
        def __init__(self, **_kwargs) -> None:
            pass

        def predict(self, _image_path: Path) -> dict[str, object]:
            return {
                "score": 0.93,
                "confidence": 0.93,
                "mask": np.array([[0, 1], [0, 1]], dtype=bool),
            }

    checkpoint = tmp_path / "stfpm_capsule.xml"
    checkpoint.write_text("<xml />", encoding="utf-8")
    monkeypatch.setattr(service_runs, "AnomalibMVTecBackend", FakeMVTecBackend)
    monkeypatch.setattr(
        service_runs,
        "_resolve_mvtec_checkpoint",
        lambda _checkpoint=None: checkpoint,
    )

    detail = service_runs.create_run_from_upload(
        "010.png",
        b"not-read-by-fake-predictor",
        mode="image",
        dataset="mvtec",
        object_name="capsule",
        defect_type="crack",
        top_k=2,
        runs_dir=tmp_path / "web_sessions",
    )

    assert detail.run.mode == "image"
    assert detail.run.dataset == "mvtec"
    assert detail.run.case_count == 1
    assert detail.evidence is not None
    assert detail.evidence["dataset"] == "mvtec"
    assert detail.evidence["object"] == "capsule"
    assert detail.evidence["anomaly_type"] == "crack"
    assert detail.analysis is not None
    assert detail.artifacts["records_path"].endswith("mvtec_image_records.jsonl")


def test_what_if_request_clears_stale_observations_and_runs_analysis() -> None:
    """The what-if API should re-run analysis from edited top-level evidence fields."""
    result = what_if_request(
        WhatIfRequest(
            case_id="mvtec_0001",
            anomaly_type="scratch",
            location="surface",
            morphology="linear",
            variables=["XMEAS_1"],
            log_events=["alarm_a"],
            top_k=2,
        )
    )

    assert result["evidence"]["case_id"] == "mvtec_0001"
    assert result["evidence"]["observations"] == []
    assert result["analysis"]["case_id"] == "mvtec_0001"


def test_feedback_record_is_appended_to_jsonl(tmp_path: Path) -> None:
    """Feedback submissions should persist as JSONL for later review."""
    output_path = tmp_path / "feedback.jsonl"
    receipt = record_feedback(
        FeedbackRequest(
            case_id="mvtec_0001",
            target_type="path",
            target_id="path_123",
            decision="accept",
            comment="good candidate",
        ),
        output_path=output_path,
    )

    assert receipt["status"] == "recorded"
    assert output_path.exists()
    saved = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert saved[0]["case_id"] == "mvtec_0001"
    assert saved[0]["target_id"] == "path_123"


def test_fastapi_routes_are_wired() -> None:
    """The API app should expose the documented local routes."""
    client = TestClient(app)

    health = client.get("/api/health")
    cases = client.get("/api/cases")
    case = client.get("/api/cases/mvtec_0001")
    analysis = client.post(
        "/api/what-if",
        json={
            "case_id": "mvtec_0001",
            "anomaly_type": "scratch",
            "location": "surface",
            "morphology": "linear",
            "variables": [],
            "log_events": [],
            "top_k": 2,
        },
    )

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert cases.status_code == 200
    assert any(item["case_id"] == "mvtec_0001" for item in cases.json())
    assert case.status_code == 200
    assert case.json()["case"]["case_id"] == "mvtec_0001"
    assert analysis.status_code == 200
    assert analysis.json()["analysis"]["case_id"] == "mvtec_0001"
