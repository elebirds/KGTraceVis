"""Tests for the KGTraceVis FastAPI service."""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import cast

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
    ReviewLedgerListRequest,
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
        target_id = request.target_id or request.case_id or request.run_id or request.target_type
        metadata = dict(request.metadata or {})
        record = {
            "feedback_id": str(uuid.uuid4()),
            "created_at": "2026-05-17T00:00:00+00:00",
            **request.model_dump(mode="json"),
            "action": request.review_action(),
            "note": request.review_note(),
            "target_id": target_id,
            "target_key": f"{request.target_type}:{target_id}",
            "source": request.source or "test",
            "metadata": metadata,
        }
        self.feedback.append(record)
        return {"status": "recorded", "record": record}

    def list_feedback(
        self,
        request: ReviewLedgerListRequest | dict[str, object],
    ) -> dict[str, object]:
        if isinstance(request, dict):
            run_id = request.get("run_id")
            case_id = request.get("case_id")
            target_type = request.get("target_type")
            target_id = request.get("target_id")
            offset = int(cast(int | str, request.get("offset", 0)))
            limit = int(cast(int | str, request.get("limit", 50)))
        else:
            run_id = request.run_id
            case_id = request.case_id
            target_type = request.target_type
            target_id = request.target_id
            offset = request.offset
            limit = request.limit

        filtered = [
            {
                "feedback_id": str(record["feedback_id"]),
                "created_at": str(record["created_at"]),
                "run_id": record.get("run_id"),
                "case_id": record.get("case_id"),
                "target_type": record.get("target_type"),
                "target_id": record.get("target_id"),
                "target_key": record.get("target_key"),
                "action": record.get("action"),
                "note": record.get("note"),
                "reviewer": record.get("reviewer"),
                "source": record.get("source") or "test",
                "metadata": record.get("metadata") or None,
            }
            for record in self.feedback
            if (run_id is None or record.get("run_id") == run_id)
            and (case_id is None or record.get("case_id") == case_id)
            and (target_type is None or record.get("target_type") == target_type)
            and (target_id is None or record.get("target_id") == target_id)
        ]
        page = filtered[offset : offset + limit]
        return {
            "records": page,
            "total_count": len(filtered),
            "returned_count": len(page),
            "offset": offset,
            "limit": limit,
            "claim_boundary": (
                "candidate/plausible explanation only; not a verified root-cause label"
            ),
        }


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
    assert "top_k_paths" in detail["analysis"]
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
    assert "top_k_paths" in payload
    assert "source_edge_provenance" in payload
    assert "review_targets" in payload
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


def test_upload_run_uses_tep_root_kgd_reasoner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEP records upload should use the single supported Root-KGD provider."""
    monkeypatch.setattr(service_runs, "DEFAULT_RUNS_DIR", tmp_path / "rootlens_sessions")

    detail = service_runs.create_run_from_upload(
        "tep_records.jsonl",
        _tep_record_jsonl_bytes(),
        mode="records",
        dataset="tep",
        top_k=2,
    )

    assert detail.run.dataset == "tep"
    assert detail.summary is not None
    assert detail.summary["pipeline"]["tep_rca_reasoner"] == "tep_root_kgd"
    assert detail.cases is not None
    ranked = detail.cases[0]["ranked_root_causes"]
    assert ranked
    assert ranked[0]["candidate_id"] == "faultanchor:stream_1_a_feed_loss"
    assert ranked[0]["scoring_method"] == "tep_root_kgd"


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
        "image_path": "runs/real_model_pipeline/assets/mvtec/input_root/capsule/test/crack/000.png",
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

    class _FakeMVTecUploadPredictor:
        def predict(self, _image_path: Path) -> dict[str, object]:
            return {
                "score": 0.71,
                "confidence": 0.71,
                "metadata": {"fixture": "service_upload"},
            }

    monkeypatch.setattr(service_api, "create_run_from_upload", _patched_create_run_from_upload)
    monkeypatch.setattr(
        service_runs,
        "_build_mvtec_upload_predictor",
        lambda **_kwargs: _FakeMVTecUploadPredictor(),
    )
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
    assert presets["auto"]["resolved_preset"] == "patchcore"
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
        "root_cause_candidate",
    ]
    assert payload["reasoning_profile_options"]["mvtec"][0]["profile_id"] == (
        "generic_graph_path_default"
    )
    assert payload["reasoning_profile_options"]["tep"][-1]["profile_id"] == (
        "tep_root_kgd_default"
    )
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
        b"version https://git-lfs.github.com/spec/v1\noid sha256:0123456789abcdef\nsize 123456\n"
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
            "assets": {"mvtec_patchcore": {"checkpoint": "checkpoint.ckpt"}},
        }

    monkeypatch.setattr(service_api, "download_model_assets", _patched_download_model_assets)

    client = TestClient(app)
    response = client.post("/api/model-assets/download", json={})

    assert response.status_code == 200
    assert captured == {"models": ("mvtec-patchcore",), "force": False}
    assert response.json()["assets"]["mvtec_patchcore"]["checkpoint"] == "checkpoint.ckpt"


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


def test_feedback_list_route_returns_review_ledger() -> None:
    """Dashboard clients should be able to read review ledger history."""
    client = TestClient(app)
    post_response = client.post(
        "/api/feedback",
        json={
            "case_id": "mvtec_0001",
            "target_type": "root_cause_candidate",
            "target_id": "rca_mvtec_0001_mechanicalcontact",
            "action": "accept",
            "source": "rootlens-dashboard",
        },
    )

    response = client.get("/api/feedback?target_type=root_cause_candidate")

    assert post_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 1
    assert payload["records"][0]["target_type"] == "root_cause_candidate"


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


def test_evidence_upload_persists_summary_pipeline_reasoning_metadata(tmp_path: Path, monkeypatch) -> None:
    """Single-evidence uploads should expose stable summary/case reasoning metadata."""
    monkeypatch.setattr(service_runs, "DEFAULT_RUNS_DIR", tmp_path / "rootlens_sessions")

    detail = service_runs.create_run_from_upload(
        "mvtec_0001.json",
        Path("data/examples/ds_mvtec_example.json").read_bytes(),
        mode="evidence",
        top_k=2,
    )

    assert detail.summary is not None
    assert detail.summary["pipeline"]["reasoning_profile_id"] == "generic_graph_path_default"
    assert detail.summary["pipeline"]["reasoner_adapter"] == "generic_graph_path"
    assert detail.summary["pipeline"]["selection_mode"] == "default"
    assert detail.reasoning_metadata["reasoning_profile_id"] == "generic_graph_path_default"
    assert detail.cases[0]["reasoning_metadata"]["reasoner_adapter"] == "generic_graph_path"


def test_records_upload_route_keeps_explicit_reasoning_profile_in_run_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit profile selection should survive upload response and persisted run reads."""
    monkeypatch.setattr(service_runs, "DEFAULT_RUNS_DIR", tmp_path / "rootlens_sessions")

    client = TestClient(app)
    with Path("data/examples/records/mvtec_records.jsonl").open("rb") as handle:
        response = client.post(
            "/api/runs/upload",
            files={"file": ("mvtec_records.jsonl", handle, "application/jsonl")},
            data={
                "mode": "records",
                "dataset": "mvtec",
                "reasoning_profile_id": "generic_graph_path_default",
                "top_k": "2",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["pipeline"]["reasoning_profile_id"] == "generic_graph_path_default"
    assert payload["summary"]["pipeline"]["selection_mode"] == "explicit"
    assert payload["cases"][0]["reasoning_metadata"]["selection_mode"] == "explicit"

    run_id = payload["run"]["run_id"]
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["summary"]["pipeline"]["reasoning_profile_id"] == (
        "generic_graph_path_default"
    )
    assert detail_payload["summary"]["pipeline"]["selection_mode"] == "explicit"
    assert detail_payload["cases"][0]["reasoning_metadata"]["reasoning_profile_id"] == (
        "generic_graph_path_default"
    )


def test_kg_construction_validate_route_returns_qa_report(tmp_path: Path, monkeypatch) -> None:
    """Construction validate route should expose the RootLens qa_report field."""
    run_id = _write_fake_construction_build(tmp_path, qa_status="passed")
    monkeypatch.setattr(service_kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(f"/api/kg/construction/builds/{run_id}/validate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["qa_report"]["status"] == "passed"
    assert payload["report"]["status"] == "passed"


def test_kg_construction_publish_route_accepts_confirm_publish_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publish route should accept RootLens request aliases and return path fields."""
    run_id = _write_fake_construction_build(tmp_path, qa_status="ready")
    monkeypatch.setattr(service_kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        f"/api/kg/construction/builds/{run_id}/publish",
        json={
            "dry_run": False,
            "include_defaults": False,
            "confirm_publish": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["import_summary"]["dry_run"] is False
    assert payload["include_defaults"] is False
    assert payload["node_paths"] == [str(tmp_path / run_id / "nodes.csv")]
    assert payload["edge_paths"] == [str(tmp_path / run_id / "edges.csv")]


def test_kg_construction_review_route_updates_review_queue_and_qa_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Construction edge review should update counters and remain visible after refresh."""
    run_id = _write_fake_construction_build(tmp_path, qa_status="pending")
    monkeypatch.setattr(service_kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", tmp_path)

    client = TestClient(app)
    queue_response = client.get(f"/api/kg/construction/builds/{run_id}/review-queue")
    assert queue_response.status_code == 200
    target_key = queue_response.json()["edges"][0]["target_key"]

    review_response = client.post(
        f"/api/kg/construction/builds/{run_id}/review",
        json={
            "action": "accept",
            "target_key": target_key,
            "reviewer": "rootlens-frontend",
        },
    )

    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["decision"]["target_key"] == target_key
    assert review_payload["edge"]["review_status"] == "reviewed"
    assert review_payload["edge"]["accepted_count"] == 1

    refreshed_queue = client.get(f"/api/kg/construction/builds/{run_id}/review-queue")
    assert refreshed_queue.status_code == 200
    edge = refreshed_queue.json()["edges"][0]
    assert edge["target_key"] == target_key
    assert edge["review_status"] == "reviewed"
    assert edge["feedback_count"] == 1
    assert edge["accepted_count"] == 1

    validation_response = client.post(f"/api/kg/construction/builds/{run_id}/validate")
    assert validation_response.status_code == 200
    assert validation_response.json()["qa_report"]["last_review"]["target_key"] == target_key


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


def _manual_rca_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "ApiManualFault,API manual fault,FaultEvent,,,,tep,manual fault row,0.71",
            "ApiManualCause,API manual cause,RootCause,,,,tep,manual cause row,0.71",
            (
                ",,,ApiManualFault,SUGGESTS_ROOT_CAUSE,ApiManualCause,tep,"
                "root cause API row,0.71"
            ),
            "",
        ]
    )


def _manual_overlay_validation_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            (
                "ApiOverlayAlert,API overlay alert,FaultType,,,,shared,"
                "overlay alert source row,0.88"
            ),
            (
                "ApiOverlayCause,API overlay cause,RootCause,,,,shared,"
                "overlay cause source row,0.88"
            ),
            (
                ",,,ApiOverlayAlert,CAUSES,ApiOverlayCause,shared,"
                "overlay RCA source row,0.88"
            ),
            "",
        ]
    )


def _write_overlay_validation_examples(tmp_path: Path) -> Path:
    example_dir = tmp_path / "overlay_examples"
    example_dir.mkdir()
    payload = {
        "case_id": "api_overlay_case",
        "dataset": "mvtec",
        "source": "unknown",
        "object": "pump",
        "anomaly_type": "API overlay alert",
        "location": None,
        "morphology": None,
        "severity": 0.7,
        "confidence": 0.8,
        "timestamp": None,
        "raw_evidence": {
            "variables": [],
            "variable_contributions": {},
            "log_events": [],
            "description": "API overlay validation fixture.",
        },
        "normalized_evidence": {},
        "kg_analysis": {},
    }
    (example_dir / "api_overlay_case.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return example_dir


def _manual_alignment_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,scenario,evidence,confidence",
            "PumpA,Feed pump,Equipment,shared,pump A source row,0.90",
            "PumpB,Feed pump,Equipment,shared,pump B duplicate row,0.87",
            "",
        ]
    )


def _rewrite_edges_as_required_columns(path: Path) -> None:
    required_columns = [
        "head",
        "relation",
        "tail",
        "scenario",
        "source",
        "evidence",
        "confidence",
        "weight",
        "review_status",
        "feedback_count",
        "accepted_count",
        "rejected_count",
    ]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=required_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in required_columns})


def _write_tep_rca_graph_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    rca_dir = tmp_path / "tep_rca_graph"
    rca_dir.mkdir()
    nodes_path = rca_dir / "nodes.jsonl"
    edges_path = rca_dir / "edges.jsonl"
    nodes_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "node_id": "component:component_a",
                        "entity_type": "Component",
                        "name": "Component A",
                        "candidate_role": "composition_anchor",
                        "root_cause_candidate": True,
                        "provenance_ids": ["ev_component"],
                    }
                ),
                json.dumps(
                    {
                        "node_id": "fault_anchor:fault_06",
                        "entity_type": "FaultAnchor",
                        "name": "Fault 06 anchor",
                        "candidate_role": "fault_anchor",
                        "provenance_ids": ["ev_fault"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    edges_path.write_text(
        json.dumps(
            {
                "edge_id": "rca_edge_api_unit",
                "head_id": "component:component_a",
                "relation": "CAUSES",
                "tail_id": "fault_anchor:fault_06",
                "confidence": 0.71,
                "relation_family": "FAULT_SOURCE",
                "propagation_enabled": True,
                "edge_origin": "curated_bridge",
                "provenance_ids": ["ev_edge"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return rca_dir, nodes_path, edges_path


def _tep_record_jsonl_bytes() -> bytes:
    return (
        json.dumps(
            {
                "dataset": "tep",
                "case_id": "tep_native_upload",
                "object": "process",
                "anomaly_type": "process_fault",
                "location": "reactor",
                "variables": ["XMEAS_1", "XMV_3"],
                "variable_contributions": {"XMEAS_1": 0.7, "XMV_3": 0.3},
                "fault_number": 6,
                "confidence": 0.75,
            }
        )
        + "\n"
    ).encode("utf-8")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_fake_construction_build(
    build_root: Path,
    *,
    run_id: str = "fake-construction-build",
    qa_status: str = "passed",
) -> str:
    output_dir = build_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nodes.csv").write_text(
        "id,name,label,scenario,aliases,description\n"
        "ScratchDefect,Scratch defect,AnomalyType,mvtec,scratch,Test node\n",
        encoding="utf-8",
    )
    (output_dir / "edges.csv").write_text(
        "head,relation,tail,scenario,source,evidence,confidence,weight,"
        "review_status,feedback_count,accepted_count,rejected_count\n"
        "ScratchDefect,HAS_PLAUSIBLE_CAUSE,MechanicalContact,mvtec,test,evidence,"
        "0.8,0.2,auto,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "qa_report.json").write_text(
        json.dumps({"status": qa_status}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "validation_report.json").write_text(
        json.dumps({"status": qa_status, "validated": True}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "source_kg_build_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "built",
                "created_at": "2026-05-17T00:00:00+00:00",
                "source_count": 1,
                "source_ids": ["fixture_source"],
                "node_count": 1,
                "edge_count": 1,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "source_kg_build_manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "built"}, indent=2),
        encoding="utf-8",
    )
    return run_id
