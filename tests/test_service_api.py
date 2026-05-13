"""Tests for the KGTraceVis FastAPI service."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from kgtracevis.producers.backends import AMAZON_PATCHCORE_BACKEND, ANOMALIB_ENGINE_BACKEND
from kgtracevis.service import api as service_api
from kgtracevis.service import dashboard as service_dashboard
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
    """The API case index should expose both example and real pipeline evidence."""
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
    assert payload["evidence_summary"]
    assert payload["top_k_paths"]
    assert payload["source_edge_provenance"]
    assert any(target["target_type"] == "path" for target in payload["review_targets"])
    assert all("target_key" in target for target in payload["review_targets"])


def test_upload_run_prepares_visual_evidence_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Record uploads should expose browser-safe visual evidence previews."""
    original = service_api.create_run_from_upload
    original_get_artifact_path = service_api.get_run_artifact_path

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original(*args, **kwargs)

    def _patched_get_run_artifact_path(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original_get_artifact_path(*args, **kwargs)

    monkeypatch.setattr(service_api, "create_run_from_upload", _patched_create_run_from_upload)
    monkeypatch.setattr(service_api, "get_run_artifact_path", _patched_get_run_artifact_path)
    client = TestClient(app)

    mvtec_record = {
        "dataset": "mvtec",
        "case_id": "mvtec_visual_fixture",
        "object": "capsule",
        "defect_type": "crack",
        "source_label": "crack",
        "image_path": "runs/real_model_pipeline/assets/mvtec/input_root/capsule/test/"
        "crack/000.png",
        "source_path": "runs/real_model_pipeline/assets/mvtec/input_root/capsule/test/"
        "crack/000.png",
        "mask_path": "runs/real_model_pipeline/assets/mvtec/generated_records/"
        "mvtec_capsule_test_crack_000_mask.json",
        "heatmap_path": "runs/real_model_pipeline/assets/mvtec/generated_records/"
        "mvtec_capsule_test_crack_000_heatmap.json",
        "confidence": 0.6,
    }
    wafer_record = {
        "dataset": "wafer",
        "adapter": "wm811k",
        "case_id": "wafer_visual_fixture",
        "wafer_id": "WVIS-1",
        "predicted_pattern": "Loc",
        "failure_pattern": "Loc",
        "classification_confidence": 0.67,
        "wafer_map": [[0, 0, 0], [0, 2, 0], [0, 0, 0]],
    }
    records_path = tmp_path / "visual_records.jsonl"
    records_path.write_text(
        json.dumps(mvtec_record) + "\n" + json.dumps(wafer_record) + "\n",
        encoding="utf-8",
    )

    with records_path.open("rb") as handle:
        response = client.post(
            "/api/runs/upload",
            files={"file": ("visual_records.jsonl", handle, "application/jsonl")},
            data={"mode": "records", "top_k": "2"},
        )

    assert response.status_code == 200
    payload = response.json()
    visual_items = payload["visual_evidence"]
    kinds = {item["kind"] for item in visual_items if item["available"]}
    assert {"image", "mask", "heatmap", "wafer_map"} <= kinds
    artifact_prefix = f"/api/runs/{payload['run']['run_id']}/artifacts/"
    assert all(
        item["url"].startswith(artifact_prefix) for item in visual_items if item["available"]
    )

    first_url = next(item["url"] for item in visual_items if item["kind"] == "wafer_map")
    artifact_response = client.get(first_url)
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"] == "image/png"


def test_default_run_store_prefers_rootlens_and_reads_legacy(
    tmp_path: Path,
) -> None:
    """Dashboard run discovery should use RootLens sessions while reading legacy runs."""
    rootlens_detail = service_runs.create_run_from_upload(
        "mvtec_records.jsonl",
        Path("data/examples/records/mvtec_records.jsonl").read_bytes(),
        mode="records",
        top_k=2,
        runs_dir=tmp_path / "rootlens_sessions",
    )
    legacy_detail = service_runs.create_run_from_upload(
        "wafer_record.jsonl",
        Path("data/examples/records/wm811k_records.jsonl").read_bytes(),
        mode="records",
        top_k=2,
        runs_dir=tmp_path / "web_sessions",
    )

    monkeypatch_dirs = (tmp_path / "rootlens_sessions", tmp_path / "web_sessions")
    original_default = service_runs.DEFAULT_RUNS_DIR
    original_legacy = service_runs.LEGACY_WEB_RUNS_DIR
    try:
        service_runs.DEFAULT_RUNS_DIR = monkeypatch_dirs[0]
        service_runs.LEGACY_WEB_RUNS_DIR = monkeypatch_dirs[1]
        runs = service_runs.list_runs()
        assert {run.run_id for run in runs} == {
            rootlens_detail.run.run_id,
            legacy_detail.run.run_id,
        }
        assert service_runs.get_run_detail(legacy_detail.run.run_id).run.run_id == (
            legacy_detail.run.run_id
        )
    finally:
        service_runs.DEFAULT_RUNS_DIR = original_default
        service_runs.LEGACY_WEB_RUNS_DIR = original_legacy


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
                "model_preset": "stfpm",
                "top_k": "2",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["mode"] == "image"
    assert payload["evidence"]["anomaly_type"] == "unknown"
    assert payload["evidence"]["morphology"] is None


def test_mvtec_model_preset_route_reports_available_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The API should expose selectable MVTec model presets for image uploads."""
    checkpoint = tmp_path / "efficientad.pt"
    checkpoint.write_bytes(b"trusted local checkpoint placeholder")
    monkeypatch.setenv("KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT", str(checkpoint))

    client = TestClient(app)
    response = client.get("/api/runs/mvtec-model-presets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_preset"] == "auto"
    presets = {item["preset"]: item for item in payload["presets"]}
    assert presets["auto"]["resolved_preset"] == "efficientad"
    assert presets["efficientad"]["available"] is True


def test_dashboard_bootstrap_route_exposes_contract(monkeypatch) -> None:
    """RootLens clients should get stable initialization metadata from one endpoint."""
    monkeypatch.setattr(service_dashboard, "list_runs", lambda *args, **kwargs: [])
    client = TestClient(app)

    response = client.get("/api/dashboard/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["claim_boundary"].startswith("candidate/plausible explanation")
    assert {item["mode"] for item in payload["upload_modes"]} == {
        "evidence",
        "records",
        "image",
    }
    assert payload["supported_feedback_targets"] == [
        "path",
        "edge",
        "entity_link",
        "correction",
    ]
    assert "presets" in payload["mvtec_model_presets"]


def test_mvtec_model_preset_route_detects_makefile_patchcore_asset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The model preset route should recognize make download-patchcore output."""
    monkeypatch.chdir(tmp_path)
    checkpoint = (
        tmp_path
        / "runs"
        / "real_model_pipeline"
        / "assets"
        / "mvtec"
        / "checkpoints"
        / "mvtec_patchcore.ckpt"
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"trusted local checkpoint placeholder")

    client = TestClient(app)
    response = client.get("/api/runs/mvtec-model-presets")

    assert response.status_code == 200
    presets = {item["preset"]: item for item in response.json()["presets"]}
    assert presets["auto"]["resolved_preset"] == "patchcore"
    assert presets["patchcore"]["available"] is True
    assert presets["patchcore"]["checkpoint_path"].endswith(
        "runs/real_model_pipeline/assets/mvtec/checkpoints/mvtec_patchcore.ckpt"
    )


def test_mvtec_model_preset_route_detects_amazon_patchcore_artifact_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The model preset route should recognize official Amazon PatchCore artifacts."""
    checkpoint = tmp_path / "models" / "mvtec_bottle"
    checkpoint.mkdir(parents=True)
    (checkpoint / "patchcore_params.pkl").write_bytes(b"params")
    (checkpoint / "nnscorer_search_index.faiss").write_bytes(b"faiss")
    monkeypatch.setenv("KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT", str(checkpoint))

    client = TestClient(app)
    response = client.get("/api/runs/mvtec-model-presets")

    assert response.status_code == 200
    presets = {item["preset"]: item for item in response.json()["presets"]}
    assert presets["patchcore"]["available"] is True
    assert presets["patchcore"]["backend"] == "amazon-patchcore"
    assert presets["patchcore"]["checkpoint_path"] == str(checkpoint)


def test_mvtec_model_preset_route_detects_amazon_patchcore_artifact_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The model preset route should recognize full official PatchCore object roots."""
    root = tmp_path / "models"
    checkpoint = root / "mvtec_bottle"
    checkpoint.mkdir(parents=True)
    (checkpoint / "patchcore_params.pkl").write_bytes(b"params")
    (checkpoint / "nnscorer_search_index.faiss").write_bytes(b"faiss")
    monkeypatch.setenv("KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT", str(root))

    client = TestClient(app)
    response = client.get("/api/runs/mvtec-model-presets")

    assert response.status_code == 200
    presets = {item["preset"]: item for item in response.json()["presets"]}
    assert presets["patchcore"]["available"] is True
    assert presets["patchcore"]["backend"] == "amazon-patchcore"
    assert presets["patchcore"]["checkpoint_path"] == str(root)


def test_mvtec_model_preset_route_ignores_amazon_patchcore_lfs_pointers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Lightweight Git LFS clones should not make PatchCore look available."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT", raising=False)
    monkeypatch.delenv("KGTRACEVIS_MVTEC_STFPM_CHECKPOINT", raising=False)
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0123456789abcdef\n"
        b"size 123456\n"
    )
    root = tmp_path / "models"
    checkpoint = root / "mvtec_bottle"
    checkpoint.mkdir(parents=True)
    (checkpoint / "patchcore_params.pkl").write_bytes(pointer)
    (checkpoint / "nnscorer_search_index.faiss").write_bytes(pointer)
    monkeypatch.setenv("KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT", str(root))

    client = TestClient(app)
    response = client.get("/api/runs/mvtec-model-presets")

    assert response.status_code == 200
    presets = {item["preset"]: item for item in response.json()["presets"]}
    assert presets["patchcore"]["available"] is False
    assert presets["patchcore"]["checkpoint_path"] is None
    assert presets["auto"]["resolved_preset"] is None


def test_model_asset_download_route_uses_default_asset(monkeypatch) -> None:
    """The API should expose a trusted default model asset download action."""
    captured: dict[str, object] = {}

    def _patched_download_model_assets(*, models, force=False):
        captured["models"] = models
        captured["force"] = force
        return {
            "artifact_type": "model_asset_download_v0",
            "assets_root": "runs/real_model_pipeline/assets",
            "assets": {"mvtec_stfpm": {"checkpoint": "checkpoint.xml"}},
        }

    monkeypatch.setattr(service_api, "download_model_assets", _patched_download_model_assets)

    client = TestClient(app)
    response = client.post("/api/model-assets/download", json={})

    assert response.status_code == 200
    assert captured == {"models": ("mvtec-stfpm",), "force": False}
    assert response.json()["assets"]["mvtec_stfpm"]["checkpoint"] == "checkpoint.xml"


def test_model_asset_download_route_rejects_unknown_asset() -> None:
    """The download route should only accept configured trusted model assets."""
    client = TestClient(app)
    response = client.post("/api/model-assets/download", json={"models": ["unknown-model"]})

    assert response.status_code == 400
    assert "model asset must be one of" in response.json()["detail"]


def test_image_upload_missing_requested_model_preset_returns_400(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Selecting an unavailable preset should fail before fake evidence is produced."""
    original = service_api.create_run_from_upload

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "web_sessions"
        return original(*args, **kwargs)

    monkeypatch.setattr(service_api, "create_run_from_upload", _patched_create_run_from_upload)
    monkeypatch.setenv(
        "KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT",
        str(tmp_path / "missing_efficientad.pt"),
    )

    client = TestClient(app)
    response = client.post(
        "/api/runs/upload",
        files={"file": ("010.png", b"not-read", "image/png")},
        data={
            "mode": "image",
            "dataset": "mvtec",
            "object_name": "capsule",
            "model_preset": "efficientad",
            "top_k": "2",
        },
    )

    assert response.status_code == 400
    assert "efficientad" in response.json()["detail"]


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

    checkpoint = tmp_path / "patchcore.ckpt"
    checkpoint.write_text("<xml />", encoding="utf-8")
    monkeypatch.setenv("KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT", str(checkpoint))
    monkeypatch.setattr(service_runs, "AnomalibMVTecBackend", FakeMVTecBackend)

    detail = service_runs.create_run_from_upload(
        "010.png",
        b"not-read-by-fake-predictor",
        mode="image",
        dataset="mvtec",
        object_name="capsule",
        defect_type="crack",
        model_preset="patchcore",
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
    assert detail.run.model_preset == "patchcore"
    assert detail.run.model_backend == ANOMALIB_ENGINE_BACKEND
    assert detail.analysis is not None
    assert detail.artifacts["records_path"].endswith("mvtec_image_records.jsonl")
    assert detail.artifacts["model_preset"] == "patchcore"


def test_image_upload_mode_resolves_amazon_patchcore_object_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Image uploads should select the uploaded object's official artifact dir."""
    captured: dict[str, object] = {}

    class FakeAmazonPatchCoreBackend:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def predict(self, _image_path: Path) -> dict[str, object]:
            return {
                "score": 0.84,
                "confidence": 0.84,
                "mask": np.array([[1, 0], [1, 0]], dtype=bool),
                "metadata": {"fixture": "amazon-patchcore"},
            }

    root = tmp_path / "models"
    capsule_checkpoint = root / "mvtec_capsule"
    capsule_checkpoint.mkdir(parents=True)
    (capsule_checkpoint / "patchcore_params.pkl").write_bytes(b"params")
    (capsule_checkpoint / "nnscorer_search_index.faiss").write_bytes(b"faiss")
    monkeypatch.setenv("KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT", str(root))
    monkeypatch.setattr(service_runs, "AmazonPatchCoreBackend", FakeAmazonPatchCoreBackend)

    detail = service_runs.create_run_from_upload(
        "010.png",
        b"not-read-by-fake-predictor",
        mode="image",
        dataset="mvtec",
        object_name="capsule",
        defect_type=None,
        model_preset="patchcore",
        top_k=2,
        runs_dir=tmp_path / "web_sessions",
    )

    assert captured["checkpoint"] == capsule_checkpoint
    assert detail.run.model_backend == AMAZON_PATCHCORE_BACKEND
    assert detail.artifacts["checkpoint_path"] == str(capsule_checkpoint)
    assert detail.evidence is not None
    assert detail.evidence["object"] == "capsule"


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
    assert saved[0]["action"] == "accept"


def test_review_feedback_contract_accepts_dashboard_actions(tmp_path: Path) -> None:
    """Dashboard review actions should persist without mutating the base KG."""
    output_path = tmp_path / "feedback.jsonl"
    receipt = record_feedback(
        FeedbackRequest(
            run_id="run_123",
            case_id="mvtec_0001",
            target_type="edge",
            target_id="ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec",
            action="needs_review",
            note="expert wants source checked",
            reviewer="analyst",
            source="rootlens-dashboard",
        ),
        output_path=output_path,
    )

    assert receipt["status"] == "recorded"
    saved = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert saved[0]["target_type"] == "edge"
    assert saved[0]["action"] == "needs_review"
    assert saved[0]["note"] == "expert wants source checked"
    assert saved[0]["source"] == "rootlens-dashboard"


def test_fastapi_routes_are_wired() -> None:
    """The API app should expose the documented local routes."""
    client = TestClient(app)

    health = client.get("/api/health")
    bootstrap = client.get("/api/dashboard/bootstrap")
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
    assert bootstrap.status_code == 200
    assert bootstrap.json()["status"] == "ok"
    assert cases.status_code == 200
    assert any(item["case_id"] == "mvtec_0001" for item in cases.json())
    assert case.status_code == 200
    assert case.json()["case"]["case_id"] == "mvtec_0001"
    assert analysis.status_code == 200
    assert analysis.json()["analysis"]["case_id"] == "mvtec_0001"
