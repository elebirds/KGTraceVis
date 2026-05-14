"""Tests for the KGTraceVis FastAPI service."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from kgtracevis.producers.backends import AMAZON_PATCHCORE_BACKEND, ANOMALIB_ENGINE_BACKEND
from kgtracevis.service import api as service_api
from kgtracevis.service import dashboard as service_dashboard
from kgtracevis.service import kg_construction as service_kg_construction
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


class InMemoryRunStore:
    """Small test double for the Postgres run store contract."""

    def __init__(self) -> None:
        self.details: dict[str, service_runs.RunDetail] = {}
        self.feedback: list[dict[str, object]] = []

    def save_run(self, detail: service_runs.RunDetail) -> service_runs.RunDetail:
        self.details[detail.run.run_id] = detail
        return detail

    def list_runs(self) -> list[service_runs.RunSummary]:
        return sorted(
            [detail.run for detail in self.details.values()],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def get_run_detail(self, run_id: str) -> service_runs.RunDetail:
        if run_id not in self.details:
            raise ValueError(f"unknown run session: {run_id}")
        return self.details[run_id]

    def get_artifact_path(self, run_id: str, artifact_name: str) -> str:
        detail = self.get_run_detail(run_id)
        artifact_path = Path(detail.run.run_dir) / "artifacts" / artifact_name
        if not artifact_path.is_file():
            raise ValueError(f"unknown run artifact: {artifact_name}")
        return str(artifact_path)

    def record_feedback(self, request: FeedbackRequest) -> dict[str, object]:
        record = {
            "feedback_id": str(uuid.uuid4()),
            **request.model_dump(mode="json"),
            "action": request.review_action(),
            "note": request.review_note(),
        }
        self.feedback.append(record)
        return {"status": "recorded", "record": record}


@pytest.fixture(autouse=True)
def postgres_run_store_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[InMemoryRunStore, None, None]:
    """Route service tests through the run-store contract without a live database."""
    store = InMemoryRunStore()
    service_runs.configure_run_store_for_testing(store)
    monkeypatch.setattr(
        "kgtracevis.service.handlers._default_feedback_store",
        lambda: store,
    )
    yield store
    service_runs.configure_run_store_for_testing(None)


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
    """Uploaded sample bundles should create reusable Postgres-backed run state."""
    original = service_api.create_run_from_upload
    original_list_runs = service_api.list_runs
    original_get_run_detail = service_api.get_run_detail

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
        return original(*args, **kwargs)

    def _patched_list_runs(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
        return original_list_runs(*args, **kwargs)

    def _patched_get_run_detail(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
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
    assert len(payload["cases"]) == 2
    assert all("path_graph" in case for case in payload["cases"])
    assert all("review_targets" in case for case in payload["cases"])

    run_id = payload["run"]["run_id"]
    assert not (tmp_path / "run_artifacts" / run_id / "manifest.json").exists()

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


def test_default_upload_run_persists_detail_to_postgres(
    tmp_path: Path,
    monkeypatch,
    postgres_run_store_fixture: InMemoryRunStore,
) -> None:
    """Default upload persistence should write run detail through the Postgres store."""
    monkeypatch.setattr(service_runs, "DEFAULT_RUNS_DIR", tmp_path / "rootlens_sessions")

    detail = service_runs.create_run_from_upload(
        "mvtec_0001.json",
        Path("data/examples/ds_mvtec_example.json").read_bytes(),
        mode="evidence",
        top_k=2,
    )

    uuid.UUID(detail.run.run_id)
    assert postgres_run_store_fixture.details[detail.run.run_id].run.run_id == detail.run.run_id
    assert not (Path(detail.run.run_dir) / "manifest.json").exists()


def test_upload_run_validates_missing_tep_artifact_provider_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service upload path should validate artifact-provider config conservatively."""
    monkeypatch.setattr(service_runs, "DEFAULT_RUNS_DIR", tmp_path / "rootlens_sessions")

    with pytest.raises(ValueError, match="tep_rca_artifact_dir"):
        service_runs.create_run_from_upload(
            "tep_0001.json",
            Path("data/examples/tep_example.json").read_bytes(),
            mode="evidence",
            top_k=2,
            tep_rca_provider="artifact",
        )


def test_kg_construction_build_route_writes_runtime_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API should trigger a narrow source-to-KG build and return artifact paths."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "unit_runtime",
            "overwrite": True,
            "run_id": "kgbuild_api_unit",
            "sources": [
                {
                    "source_id": "api_manual_unit",
                    "source_type": "manual_table",
                    "scenario": "tep",
                    "source_format": "csv",
                    "source_text": _manual_source_csv(),
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "built"
    assert payload["run_id"] == "kgbuild_api_unit"
    assert payload["summary"]["node_count"] == 2
    assert payload["summary"]["edge_count"] == 1
    assert Path(payload["nodes_path"]).is_file()
    assert Path(payload["edges_path"]).is_file()
    assert Path(payload["summary_path"]).is_file()
    assert Path(payload["manifest_path"]).is_file()


def test_kg_construction_build_route_rejects_missing_tep_paths() -> None:
    """TEP runtime construction inputs should require explicit local artifacts."""
    client = TestClient(app)

    response = client.post(
        "/api/kg/construction/build",
        json={
            "sources": [
                {
                    "source_id": "tep_semantic_unit",
                    "source_type": "tep_semantic_lift",
                    "scenario": "tep",
                }
            ]
        },
    )

    assert response.status_code == 422
    assert "tep_semantic_lift requires path" in response.text


def test_upload_run_prepares_visual_evidence_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Record uploads should expose browser-safe visual evidence previews."""
    original = service_api.create_run_from_upload
    original_get_artifact_path = service_api.get_run_artifact_path

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
        return original(*args, **kwargs)

    def _patched_get_run_artifact_path(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
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
    mvtec_image = next(
        item
        for item in visual_items
        if item["case_id"] == "mvtec_visual_fixture" and item["kind"] == "image"
    )
    assert mvtec_image["title"] == "Model visualization panel"
    assert "not the raw source image" in mvtec_image["note"]
    assert mvtec_image["metadata"]["visual_role"] == "model_visualization_panel"
    artifact_prefix = f"/api/runs/{payload['run']['run_id']}/artifacts/"
    assert all(
        item["url"].startswith(artifact_prefix) for item in visual_items if item["available"]
    )

    first_url = next(item["url"] for item in visual_items if item["kind"] == "wafer_map")
    artifact_response = client.get(first_url)
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"] == "image/png"


def test_default_run_store_reads_configured_store() -> None:
    """Default run discovery should use Postgres, not legacy filesystem sessions."""
    detail = service_runs.RunDetail(
        run=service_runs.RunSummary(
            run_id="33333333-3333-3333-3333-333333333333",
            created_at="2026-05-14T00:00:00+00:00",
            mode="records",
            source_filename="records.jsonl",
            top_k=2,
            run_dir="runs/rootlens_sessions/33333333-3333-3333-3333-333333333333",
            status="completed",
            dataset="mvtec",
            case_count=1,
            evidence_count=1,
            label="records.jsonl · 1 cases",
        ),
        workflow_steps=[],
        claim_boundary="candidate/plausible explanation only",
    )
    service_runs._run_store().save_run(detail)

    runs = service_runs.list_runs()

    assert [run.run_id for run in runs] == ["33333333-3333-3333-3333-333333333333"]
    assert service_runs.get_run_detail(runs[0].run_id).run.run_id == runs[0].run_id


def test_image_upload_mode_defaults_to_unknown_label_when_unspecified(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Raw image uploads should not require an operator defect label."""
    original = service_api.create_run_from_upload

    def _patched_create_run_from_upload(*args, **kwargs):
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
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
    captured: dict[str, dict[str, object]] = {}

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
        kwargs["runs_dir"] = tmp_path / "run_artifacts"
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
        runs_dir=tmp_path / "run_artifacts",
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
        runs_dir=tmp_path / "run_artifacts",
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


def test_feedback_record_is_persisted_to_postgres_store() -> None:
    """Feedback submissions should persist through the Postgres store contract."""
    receipt = record_feedback(
        FeedbackRequest(
            case_id="mvtec_0001",
            target_type="path",
            target_id="path_123",
            decision="accept",
            comment="good candidate",
        ),
    )

    assert receipt["status"] == "recorded"
    saved = receipt["record"]
    assert saved["case_id"] == "mvtec_0001"
    assert saved["target_id"] == "path_123"
    assert saved["action"] == "accept"


def test_review_feedback_contract_accepts_dashboard_actions() -> None:
    """Dashboard review actions should persist without mutating the base KG."""
    receipt = record_feedback(
        FeedbackRequest(
            run_id="33333333-3333-3333-3333-333333333333",
            case_id="mvtec_0001",
            target_type="edge",
            target_id="ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec",
            action="needs_review",
            note="expert wants source checked",
            reviewer="analyst",
            source="rootlens-dashboard",
        ),
    )

    assert receipt["status"] == "recorded"
    saved = receipt["record"]
    assert saved["target_type"] == "edge"
    assert saved["action"] == "needs_review"
    assert saved["note"] == "expert wants source checked"
    assert saved["source"] == "rootlens-dashboard"


def test_feedback_record_defaults_to_postgres_store(monkeypatch) -> None:
    """Feedback without an explicit output path should use Postgres persistence."""
    captured: dict[str, dict[str, object]] = {}

    class FakeStore:
        def record_feedback(self, request):
            record = {
                **request.model_dump(mode="json"),
                "action": request.review_action(),
                "note": request.review_note(),
            }
            captured["record"] = record
            return {"status": "recorded", "record": record}

    monkeypatch.setattr(
        "kgtracevis.service.handlers._default_feedback_store",
        lambda: FakeStore(),
    )

    receipt = record_feedback(
        FeedbackRequest(
            run_id="33333333-3333-3333-3333-333333333333",
            target_type="path",
            target_id="path_123",
            action="accept",
        )
    )

    assert receipt["status"] == "recorded"
    assert captured["record"]["target_type"] == "path"
    assert captured["record"]["action"] == "accept"


def test_feedback_record_requires_configured_postgres_store(monkeypatch) -> None:
    """Feedback should fail explicitly when no Postgres runtime store is configured."""
    monkeypatch.setattr(
        "kgtracevis.service.handlers._default_feedback_store",
        lambda: None,
    )

    with pytest.raises(ValueError, match="Postgres feedback store is not configured"):
        record_feedback(
            FeedbackRequest(
                run_id="33333333-3333-3333-3333-333333333333",
                target_type="path",
                target_id="path_123",
                action="accept",
            )
        )


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


def _manual_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "ApiManualSource,API manual source,Variable,,,,tep,manual source row,0.71",
            "ApiManualTarget,API manual target,ProcessUnit,,,,tep,manual target row,0.71",
            ",,,ApiManualSource,BELONGS_TO,ApiManualTarget,tep,explicit API row,0.71",
            "",
        ]
    )
