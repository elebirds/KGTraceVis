"""Tests for the KGTraceVis FastAPI service."""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from kgtracevis.kg_construction import (
    GENERIC_PROFILE,
    DraftEntity,
    DraftKG,
    build_review_queue,
    review_queue_payload,
    run_entity_alignment,
)
from kgtracevis.producers.backends import AMAZON_PATCHCORE_BACKEND, ANOMALIB_ENGINE_BACKEND
from kgtracevis.service import api as service_api
from kgtracevis.service import dashboard as service_dashboard
from kgtracevis.service import kg_construction as service_kg_construction
from kgtracevis.service import kg_materials as service_kg_materials
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
    assert Path(payload["source_library_manifest_path"]).is_file()
    assert Path(payload["draft_manifest_path"]).is_file()
    assert Path(payload["profile_manifest_path"]).is_file()
    assert Path(payload["alignment_manifest_path"]).is_file()
    assert Path(payload["source_audit_graph_manifest_path"]).is_file()
    assert Path(payload["semantic_layer_manifest_path"]).is_file()
    assert Path(payload["rca_view_manifest_path"]).is_file()
    assert Path(payload["review_queue_path"]).is_file()
    assert Path(payload["document_understanding_manifest_path"]).is_file()
    assert Path(payload["document_map_path"]).is_file()
    assert Path(payload["chunk_prompt_context_path"]).is_file()
    assert Path(payload["cross_chunk_proposals_path"]).is_file()
    assert Path(payload["publish_manifest_path"]).is_file()
    assert Path(payload["diff_path"]).is_file()

    nodes_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/nodes"
    )
    review_queue_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/review_queue"
    )
    alignment_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/alignment_manifest"
    )
    decisions_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/review_decisions"
    )
    diff_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/kg_construction_diff"
    )
    traversal_artifact = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/..%2Fnodes"
    )
    invalid_key = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/bad$key"
    )
    missing_key = client.get(
        "/api/kg/construction/builds/kgbuild_api_unit/artifacts/not_a_real_key"
    )

    assert nodes_artifact.status_code == 200
    assert "ApiManualSource" in nodes_artifact.text
    assert review_queue_artifact.status_code == 200
    assert isinstance(review_queue_artifact.json(), list)
    assert alignment_artifact.status_code == 200
    assert alignment_artifact.json()["artifact_type"] == "entity_alignment_manifest_v1"
    assert decisions_artifact.status_code == 200
    assert decisions_artifact.text == ""
    assert diff_artifact.status_code == 200
    assert diff_artifact.json()["scope"] == "fresh_build"
    assert traversal_artifact.status_code == 404
    assert invalid_key.status_code == 400
    assert missing_key.status_code == 404


def test_kg_construction_build_artifact_helper_resolves_safe_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construction artifact lookup should use stable keys, not raw paths."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    build = service_kg_construction.run_kg_construction_build(
        service_kg_construction.KGConstructionBuildRequest(
            output_name="artifact_helper_runtime",
            overwrite=True,
            run_id="kgbuild_artifact_helper_unit",
            sources=[
                service_kg_construction.KGConstructionSourceInput(
                    source_id="api_manual_unit",
                    source_type="manual_table",
                    scenario="tep",
                    source_format="csv",
                    source_text=_manual_source_csv(),
                )
            ],
        )
    )

    nodes_path = service_kg_construction.get_kg_construction_build_artifact_path(
        "kgbuild_artifact_helper_unit",
        "nodes",
    )
    queue_path = service_kg_construction.get_kg_construction_build_artifact_path(
        "kgbuild_artifact_helper_unit",
        "review_queue",
    )
    decisions_path = service_kg_construction.get_kg_construction_build_artifact_path(
        "kgbuild_artifact_helper_unit",
        "review_decisions",
    )

    assert nodes_path == Path(build.nodes_path).resolve()
    assert nodes_path.suffix == ".csv"
    assert queue_path == Path(build.review_queue_path).resolve()
    assert queue_path.suffix == ".json"
    assert decisions_path == Path(build.summary["output"]["review_decisions"]).resolve()
    assert decisions_path.suffix == ".jsonl"

    alternate_queue_path = Path(build.output_dir) / "alternate_review_queue.json"
    alternate_queue_path.write_text("[]", encoding="utf-8")
    manifest_path = Path(build.manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["review_queue"] = str(alternate_queue_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert service_kg_construction.get_kg_construction_build_artifact_path(
        "kgbuild_artifact_helper_unit",
        "review_queue",
    ) == alternate_queue_path.resolve()

    with pytest.raises(ValueError, match="unknown construction artifact key"):
        service_kg_construction.get_kg_construction_build_artifact_path(
            "kgbuild_artifact_helper_unit",
            "nodes.csv",
        )
    with pytest.raises(ValueError, match="path separators"):
        service_kg_construction.get_kg_construction_build_artifact_path(
            "kgbuild_artifact_helper_unit",
            "../nodes",
        )
    with pytest.raises(ValueError, match="is a directory"):
        service_kg_construction.get_kg_construction_build_artifact_path(
            "kgbuild_artifact_helper_unit",
            "output_dir",
        )

    alternate_queue_path.unlink()
    with pytest.raises(ValueError, match="artifact not found"):
        service_kg_construction.get_kg_construction_build_artifact_path(
            "kgbuild_artifact_helper_unit",
            "review_queue",
        )


def test_kg_construction_build_registry_lists_details_and_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construction builds should be discoverable and independently QA-able."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "registry_runtime",
            "overwrite": True,
            "run_id": "kgbuild_registry_unit",
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
    assert build_response.status_code == 200

    list_response = client.get("/api/kg/construction/builds")
    assert list_response.status_code == 200
    builds = list_response.json()["builds"]
    assert [build["run_id"] for build in builds] == ["kgbuild_registry_unit"]
    assert builds[0]["node_count"] == 2
    assert builds[0]["edge_count"] == 1
    assert builds[0]["source_library_manifest_path"].endswith(
        "source_library_manifest.json"
    )
    assert builds[0]["draft_manifest_path"].endswith("draft_manifest.json")
    assert builds[0]["profile_manifest_path"].endswith("profile_manifest.json")
    assert builds[0]["alignment_manifest_path"].endswith(
        "entity_alignment_manifest.json"
    )
    assert builds[0]["source_audit_graph_manifest_path"].endswith(
        "source_audit_graph_manifest.json"
    )
    assert builds[0]["semantic_layer_manifest_path"].endswith(
        "semantic_layer_manifest.json"
    )
    assert builds[0]["rca_view_manifest_path"].endswith("rca_view_manifest.json")
    assert builds[0]["review_queue_path"].endswith("review_queue.json")
    assert builds[0]["document_understanding_manifest_path"].endswith(
        "document_understanding_manifest.json"
    )
    assert builds[0]["document_map_path"].endswith("document_map.json")
    assert builds[0]["chunk_prompt_context_path"].endswith(
        "chunk_prompt_context.jsonl"
    )
    assert builds[0]["cross_chunk_proposals_path"].endswith(
        "cross_chunk_proposals.jsonl"
    )
    assert builds[0]["publish_manifest_path"].endswith("publish_manifest.json")

    detail_response = client.get("/api/kg/construction/builds/kgbuild_registry_unit")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["build"]["summary_path"].endswith("kg_construction_summary.json")
    assert detail["build"]["source_library_manifest_path"].endswith(
        "source_library_manifest.json"
    )
    assert detail["build"]["alignment_manifest_path"].endswith(
        "entity_alignment_manifest.json"
    )
    assert detail["build"]["review_queue_path"].endswith("review_queue.json")
    assert detail["build"]["document_map_path"].endswith("document_map.json")
    assert detail["build"]["cross_chunk_proposals_path"].endswith(
        "cross_chunk_proposals.jsonl"
    )
    assert detail["summary"]["node_count"] == 2
    assert detail["manifest"]["run"]["run_id"] == "kgbuild_registry_unit"

    validation_response = client.post("/api/kg/construction/builds/kgbuild_registry_unit/validate")
    assert validation_response.status_code == 200
    validation = validation_response.json()
    assert validation["build"]["run_id"] == "kgbuild_registry_unit"
    assert validation["qa_report"]["summary"]["passed"] is True
    assert validation["qa_report"]["summary"]["edge_count"] == 1


def test_kg_construction_overlay_validation_route_runs_runtime_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build-scoped overlay validation should expose runtime RCA readiness."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)
    example_dir = _write_overlay_validation_examples(tmp_path)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "overlay_validation_runtime",
            "overwrite": True,
            "run_id": "kgbuild_overlay_api_unit",
            "sources": [
                {
                    "source_id": "api_overlay_unit",
                    "source_type": "manual_table",
                    "scenario": "shared",
                    "source_format": "csv",
                    "source_text": _manual_overlay_validation_source_csv(),
                }
            ],
        },
    )
    assert build_response.status_code == 200

    validation_response = client.post(
        "/api/kg/construction/builds/kgbuild_overlay_api_unit/validate-overlay",
        json={"example_dir": str(example_dir), "top_k": 3},
    )
    missing_response = client.post(
        "/api/kg/construction/builds/missing_overlay_unit/validate-overlay",
        json={"example_dir": str(example_dir)},
    )

    assert validation_response.status_code == 200
    payload = validation_response.json()
    assert payload["build"]["run_id"] == "kgbuild_overlay_api_unit"
    assert Path(payload["report_path"]).is_file()
    assert payload["report"]["kg_backend"] == "explicit_seed_overlay"
    assert payload["report"]["contract_validated"] is True
    assert payload["report"]["runtime_validated"] is True
    assert payload["report"]["overlay_contributed"] is True
    assert payload["report"]["runtime_graph"]["include_defaults"] is True
    assert payload["report"]["overlay_contribution_case_count"] == 1
    assert payload["report"]["validated"] is True
    assert payload["report"]["import_dry_run"]["dry_run"] is True
    assert payload["report"]["import_dry_run"]["include_defaults"] is True
    assert payload["report"]["examples"][0]["case_id"] == "api_overlay_case"
    assert payload["report"]["examples"][0]["overlay_contributed"] is True
    assert payload["report"]["examples"][0]["top_target_entity_id"] == (
        "ApiOverlayCause"
    )
    assert payload["report"]["examples"][0]["kg_build_ids"] == [
        "kgbuild_overlay_api_unit"
    ]
    assert "does not rebuild KG" in payload["claim_boundary"]

    artifact_response = client.get(
        "/api/kg/construction/builds/kgbuild_overlay_api_unit/artifacts/"
        "kg_overlay_validation_report"
    )
    assert artifact_response.status_code == 200
    assert artifact_response.json()["artifact_type"] == (
        "kg_overlay_validation_report_v1"
    )
    assert missing_response.status_code == 404


def test_kg_construction_build_registry_supports_legacy_manifests_and_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old build manifests and required-only edge CSVs should remain readable."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "legacy_registry_runtime",
            "overwrite": True,
            "run_id": "kgbuild_legacy_registry_unit",
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
    assert build_response.status_code == 200
    payload = build_response.json()

    manifest_path = Path(payload["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "draft_manifest",
        "profile_manifest",
        "alignment_manifest",
        "source_audit_graph_manifest",
        "semantic_layer_manifest",
        "rca_view_manifest",
        "review_queue",
        "publish_manifest",
    ):
        manifest["artifacts"].pop(key)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    list_response = client.get("/api/kg/construction/builds")
    assert list_response.status_code == 200
    build = list_response.json()["builds"][0]
    assert build["source_library_manifest_path"].endswith("source_library_manifest.json")
    assert build["draft_manifest_path"].endswith("draft_manifest.json")
    assert build["profile_manifest_path"].endswith("profile_manifest.json")
    assert build["alignment_manifest_path"].endswith("entity_alignment_manifest.json")
    assert build["source_audit_graph_manifest_path"].endswith(
        "source_audit_graph_manifest.json"
    )
    assert build["semantic_layer_manifest_path"].endswith(
        "semantic_layer_manifest.json"
    )
    assert build["rca_view_manifest_path"].endswith("rca_view_manifest.json")
    assert build["review_queue_path"].endswith("review_queue.json")
    assert build["publish_manifest_path"].endswith("publish_manifest.json")

    Path(payload["review_queue_path"]).unlink()
    _rewrite_edges_as_required_columns(Path(payload["edges_path"]))
    queue_response = client.get(
        "/api/kg/construction/builds/kgbuild_legacy_registry_unit/review-queue",
        params={"relation": "BELONGS_TO"},
    )
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert queue["total_count"] == 1
    assert queue["edges"][0]["target_key"] == (
        "ApiManualSource|BELONGS_TO|ApiManualTarget|tep"
    )


def test_kg_construction_publish_route_dry_runs_merged_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construction publish should default to a read-only default+candidate dry-run."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "publish_runtime",
            "overwrite": True,
            "run_id": "kgbuild_publish_unit",
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
    assert build_response.status_code == 200

    publish_response = client.post(
        "/api/kg/construction/builds/kgbuild_publish_unit/publish",
        json={},
    )
    candidate_only_response = client.post(
        "/api/kg/construction/builds/kgbuild_publish_unit/publish",
        json={"include_defaults": False},
    )

    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["build"]["run_id"] == "kgbuild_publish_unit"
    assert payload["include_defaults"] is True
    assert payload["import_summary"]["dry_run"] is True
    assert payload["import_summary"]["node_count"] > 2
    assert payload["import_summary"]["edge_count"] > 1
    assert payload["node_paths"][-1].endswith("published_nodes.csv")
    assert payload["edge_paths"][-1].endswith("published_edges.csv")
    assert "candidate/reviewable" in payload["claim_boundary"]

    assert candidate_only_response.status_code == 200
    candidate_only = candidate_only_response.json()
    assert candidate_only["include_defaults"] is False
    assert candidate_only["import_summary"] == {
        "node_count": 0,
        "edge_count": 0,
        "dry_run": True,
    }


def test_kg_construction_publish_route_requires_confirmation_for_real_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real Neo4j publication should fail closed without explicit confirmation."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "publish_guard_runtime",
            "overwrite": True,
            "run_id": "kgbuild_publish_guard_unit",
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
    assert build_response.status_code == 200

    response = client.post(
        "/api/kg/construction/builds/kgbuild_publish_guard_unit/publish",
        json={"dry_run": False},
    )

    assert response.status_code == 400
    assert "confirm_publish=true" in response.text


def test_kg_construction_review_route_updates_edge_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge review should update the candidate CSV counters and decision log."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "review_runtime",
            "overwrite": True,
            "run_id": "kgbuild_review_unit",
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
    assert build_response.status_code == 200
    build_payload = build_response.json()
    edge_key = "ApiManualSource|BELONGS_TO|ApiManualTarget|tep"

    accept_response = client.post(
        "/api/kg/construction/builds/kgbuild_review_unit/review",
        json={
            "target_key": edge_key,
            "action": "accept",
            "reviewer": "unit-test",
            "note": "looks source-backed",
        },
    )
    reject_response = client.post(
        "/api/kg/construction/builds/kgbuild_review_unit/review",
        json={
            "head": "ApiManualSource",
            "relation": "BELONGS_TO",
            "tail": "ApiManualTarget",
            "scenario": "tep",
            "action": "reject",
            "reviewer": "unit-test",
            "note": "exercise reject path",
        },
    )

    assert accept_response.status_code == 200
    accepted = accept_response.json()
    assert accepted["edge"]["review_status"] == "reviewed"
    assert accepted["edge"]["feedback_count"] == "1"
    assert accepted["edge"]["accepted_count"] == "1"
    assert accepted["edge"]["rejected_count"] == "0"
    assert accepted["decision"]["target_key"] == edge_key
    assert accepted["decision"]["action"] == "accept"
    assert accepted["summary"]["review_status_counts"] == {"reviewed": 1}

    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["edge"]["review_status"] == "rejected"
    assert rejected["edge"]["feedback_count"] == "2"
    assert rejected["edge"]["accepted_count"] == "1"
    assert rejected["edge"]["rejected_count"] == "1"
    assert rejected["decision"]["action"] == "reject"
    assert rejected["summary"]["review_status_counts"] == {"rejected": 1}

    edge_rows = _read_csv_rows(Path(build_payload["edges_path"]))
    assert edge_rows[0]["review_status"] == "rejected"
    assert edge_rows[0]["feedback_count"] == "2"
    manifest = json.loads(Path(build_payload["manifest_path"]).read_text(encoding="utf-8"))
    decisions_path = Path(build_payload["output_dir"]) / "review_decisions.jsonl"
    decisions = [
        json.loads(line)
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    publish_report = json.loads(
        (Path(build_payload["output_dir"]) / "publish_report.json").read_text(
            encoding="utf-8"
        )
    )
    published_edges = _read_csv_rows(Path(build_payload["output_dir"]) / "published_edges.csv")
    assert [item["action"] for item in manifest["review_decisions"]] == [
        "accept",
        "reject",
    ]
    assert [item["action"] for item in decisions] == ["accept", "reject"]
    assert manifest["summary"]["review_status_counts"] == {"rejected": 1}
    assert manifest["run"]["status"] == "reviewed"
    assert publish_report["disposition_counts"] == {"rejected": 1}
    assert published_edges == []


def test_kg_construction_review_route_rejects_unknown_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown edge review targets should be explicit 404s."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "review_missing_runtime",
            "overwrite": True,
            "run_id": "kgbuild_review_missing_unit",
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
    assert build_response.status_code == 200

    response = client.post(
        "/api/kg/construction/builds/kgbuild_review_missing_unit/review",
        json={
            "target_key": "MissingHead|BELONGS_TO|MissingTail|tep",
            "action": "accept",
        },
    )

    assert response.status_code == 404
    assert "unknown construction edge target_key" in response.text


def test_kg_construction_review_queue_filters_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review queue should prefer the prioritized JSON artifact when present."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "review_queue_runtime",
            "overwrite": True,
            "run_id": "kgbuild_review_queue_unit",
            "sources": [
                {
                    "source_id": "api_manual_unit",
                    "source_type": "manual_table",
                    "scenario": "tep",
                    "source_format": "csv",
                    "source_text": _manual_rca_source_csv(),
                }
            ],
        },
    )
    assert build_response.status_code == 200

    initial_response = client.get(
        "/api/kg/construction/builds/kgbuild_review_queue_unit/review-queue",
        params={
            "review_status": "auto",
            "source": "api_manual_unit",
            "scenario": "tep",
            "relation": "SUGGESTS_ROOT_CAUSE",
            "query": "root cause",
            "limit": "10",
        },
    )
    assert initial_response.status_code == 200
    initial = initial_response.json()
    assert initial["total_count"] == 1
    assert initial["returned_count"] == 1
    assert initial["summary"]["review_status_counts"] == {"auto": 1}
    assert initial["summary"]["relation_counts"] == {"SUGGESTS_ROOT_CAUSE": 1}
    assert initial["edges"][0]["target_key"] == (
        "ApiManualFault|SUGGESTS_ROOT_CAUSE|ApiManualCause|tep"
    )
    assert initial["edges"][0]["confidence"] == 0.71
    assert initial["edges"][0]["priority"] == 100
    assert initial["edges"][0]["reason"] == (
        "causal/root-cause relation needs human confirmation"
    )
    assert initial["edges"][0]["graph_impact"].startswith(
        "can change Top-K RCA propagation paths (rca_score="
    )
    assert initial["edges"][0]["recommended_action"] == (
        "verify_direction_and_score_then_accept_or_reject"
    )

    review_response = client.post(
        "/api/kg/construction/builds/kgbuild_review_queue_unit/review",
        json={
            "target_key": "ApiManualFault|SUGGESTS_ROOT_CAUSE|ApiManualCause|tep",
            "action": "reject",
        },
    )
    assert review_response.status_code == 200

    rejected_response = client.get(
        "/api/kg/construction/builds/kgbuild_review_queue_unit/review-queue",
        params={"review_status": "rejected", "offset": "0", "limit": "1"},
    )
    empty_page_response = client.get(
        "/api/kg/construction/builds/kgbuild_review_queue_unit/review-queue",
        params={"review_status": "rejected", "offset": "1", "limit": "1"},
    )

    assert rejected_response.status_code == 200
    rejected = rejected_response.json()
    assert rejected["total_count"] == 1
    assert rejected["returned_count"] == 1
    assert rejected["edges"][0]["review_status"] == "rejected"
    assert rejected["edges"][0]["rejected_count"] == 1
    assert rejected["summary"]["review_status_counts"] == {"rejected": 1}
    assert rejected["edges"][0]["candidate_payload"]["review_status"] == "rejected"
    assert rejected["edges"][0]["candidate_payload"]["rejected_count"] == "1"

    assert empty_page_response.status_code == 200
    empty_page = empty_page_response.json()
    assert empty_page["total_count"] == 1
    assert empty_page["returned_count"] == 0
    assert empty_page["edges"] == []


def test_alignment_review_queue_items_parse_as_service_dtos() -> None:
    """Alignment review queue rows should stay parseable by service queue DTOs."""
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity:pump-a",
                source_id="alignment_service_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpA",
                name="Feed pump",
                label="Equipment",
                aliases=("asset:alias_a",),
                evidence="pump A source row",
                confidence=0.9,
            ),
            DraftEntity(
                draft_id="entity:pump-b",
                source_id="alignment_service_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpB",
                name="Feed pump",
                label="Equipment",
                evidence="duplicate pump source row",
                confidence=0.87,
            ),
            DraftEntity(
                draft_id="entity:unknown",
                source_id="alignment_service_unit",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="",
                name="Mystery equipment",
                label="Equipment",
                evidence="unresolved source row",
                confidence=0.5,
            ),
        )
    )
    alignment = run_entity_alignment(draft, GENERIC_PROFILE)
    payload = review_queue_payload(build_review_queue((), alignment=alignment))

    rows = [
        service_kg_construction._queue_edge_from_review_item(item)
        for item in payload
    ]

    assert {row.item_type for row in rows} == {
        "entity_merge_candidate",
        "unresolved_entity",
    }
    assert {row.review_status for row in rows} == {"auto"}
    assert all(row.priority and row.reason for row in rows)
    assert all(row.recommended_action for row in rows)


def test_kg_construction_review_route_accepts_alignment_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review route should handle non-edge review queue items."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)
    build_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "alignment_review_runtime",
            "overwrite": True,
            "run_id": "kgbuild_alignment_review_unit",
            "sources": [
                {
                    "source_id": "alignment_api_source",
                    "source_type": "manual_table",
                    "scenario": "shared",
                    "source_format": "csv",
                    "source_text": _manual_alignment_source_csv(),
                }
            ],
        },
    )
    assert build_response.status_code == 200

    queue_response = client.get(
        "/api/kg/construction/builds/kgbuild_alignment_review_unit/review-queue",
        params={"review_status": "auto", "query": "canonical merge"},
    )
    assert queue_response.status_code == 200
    queue_item = next(
        item
        for item in queue_response.json()["edges"]
        if item["item_type"] == "entity_merge_candidate"
    )

    review_response = client.post(
        "/api/kg/construction/builds/kgbuild_alignment_review_unit/review",
        json={
            "item_type": "entity_merge_candidate",
            "target_key": queue_item["target_key"],
            "action": "accept",
            "reviewer": "unit-test",
            "proposed_payload": {"reviewed_canonical_id": "PumpA"},
        },
    )

    assert review_response.status_code == 200
    reviewed = review_response.json()
    assert reviewed["edge"] == {}
    assert reviewed["item"]["review_status"] == "reviewed"
    assert reviewed["item"]["candidate_payload"]["reviewed_canonical_id"] == "PumpA"
    assert reviewed["decision"]["target_type"] == "entity_merge_candidate"
    assert reviewed["summary"]["review_decision_counts"] == {"accept": 1}

    reviewed_queue_response = client.get(
        "/api/kg/construction/builds/kgbuild_alignment_review_unit/review-queue",
        params={"review_status": "reviewed"},
    )
    reviewed_queue = reviewed_queue_response.json()
    assert reviewed_queue["total_count"] == 1
    assert reviewed_queue["edges"][0]["item_type"] == "entity_merge_candidate"
    assert reviewed_queue["edges"][0]["accepted_count"] == 1


def test_kg_construction_build_route_accepts_tep_rca_graph_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEP RCA graph sources should accept directory or explicit node/edge paths."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    rca_dir, rca_nodes_path, rca_edges_path = _write_tep_rca_graph_artifacts(tmp_path)
    client = TestClient(app)

    explicit_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "tep_rca_explicit_runtime",
            "overwrite": True,
            "run_id": "kgbuild_tep_rca_explicit",
            "sources": [
                {
                    "source_id": "tep_rca_explicit",
                    "source_type": "tep_rca_graph",
                    "scenario": "tep",
                    "rca_nodes_path": str(rca_nodes_path),
                    "rca_edges_path": str(rca_edges_path),
                }
            ],
        },
    )
    directory_response = client.post(
        "/api/kg/construction/build",
        json={
            "output_name": "tep_rca_dir_runtime",
            "overwrite": True,
            "run_id": "kgbuild_tep_rca_dir",
            "sources": [
                {
                    "source_id": "tep_rca_dir",
                    "source_type": "tep_rca_graph",
                    "scenario": "tep",
                    "path": str(rca_dir),
                }
            ],
        },
    )

    assert explicit_response.status_code == 200
    explicit_payload = explicit_response.json()
    assert explicit_payload["summary"]["edge_count"] == 1
    assert Path(explicit_payload["review_queue_path"]).is_file()
    manifest = json.loads(
        Path(explicit_payload["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["sources"][0]["metadata"]["nodes_path"] == str(rca_nodes_path)
    assert manifest["sources"][0]["metadata"]["edges_path"] == str(rca_edges_path)

    assert directory_response.status_code == 200
    directory_payload = directory_response.json()
    assert directory_payload["summary"]["edge_count"] == 1


def test_kg_construction_build_registry_rejects_unknown_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown construction build IDs should be explicit 404s."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        tmp_path / "source_kg_build",
    )
    client = TestClient(app)

    detail_response = client.get("/api/kg/construction/builds/missing_build")
    validation_response = client.post("/api/kg/construction/builds/missing_build/validate")

    assert detail_response.status_code == 404
    assert validation_response.status_code == 404
    assert "unknown construction build run_id" in detail_response.text


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


def test_kg_construction_source_upload_route_stores_build_ready_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploaded construction sources should be persisted and listable."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_SOURCE_DIR",
        tmp_path / "source_uploads",
    )
    client = TestClient(app)

    response = client.post(
        "/api/kg/construction/sources/upload",
        files={"file": ("manual_source.csv", _manual_source_csv(), "text/csv")},
        data={
            "source_id": "api_manual_upload",
            "source_type": "manual_table",
            "scenario": "tep",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["source_id"] == "api_manual_upload"
    assert payload["source_format"] == "csv"
    assert Path(payload["path"]).is_file()
    assert Path(payload["metadata_path"]).is_file()
    assert payload["build_source"]["path"] == payload["path"]
    assert payload["build_source"]["source_type"] == "manual_table"

    listing = client.get("/api/kg/construction/sources")
    assert listing.status_code == 200
    sources = listing.json()["sources"]
    assert [source["source_id"] for source in sources] == ["api_manual_upload"]


def test_kg_construction_source_upload_route_rejects_invalid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source upload should reject unsupported extensions before persistence."""
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_SOURCE_DIR",
        tmp_path / "source_uploads",
    )
    client = TestClient(app)

    response = client.post(
        "/api/kg/construction/sources/upload",
        files={"file": ("manual_source.txt", "not supported", "text/plain")},
        data={"source_id": "bad_upload", "source_type": "manual_table"},
    )

    assert response.status_code == 400
    assert "source upload filename must end with one of" in response.text
    assert not (tmp_path / "source_uploads").exists()


def test_kg_material_routes_upload_register_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Material library routes should expose upload and URL registration."""
    monkeypatch.setattr(
        service_kg_materials,
        "DEFAULT_SOURCE_KG_MATERIAL_DIR",
        tmp_path / "materials",
    )
    client = TestClient(app)

    upload = client.post(
        "/api/kg/materials/upload",
        files={"file": ("manual.txt", "A,CAUSES,B", "text/plain")},
        data={
            "title": "Manual note",
            "scenario": "tep",
            "source_type": "text",
            "material_id": "manual_note",
        },
    )

    assert upload.status_code == 200
    uploaded = upload.json()["material"]
    assert uploaded["material_id"] == "manual_note"
    assert uploaded["status"] == "uploaded"
    assert uploaded["source_type"] == "text"
    assert Path(uploaded["path"]).is_file()

    registered = client.post(
        "/api/kg/materials/register-url",
        json={
            "material_id": "paper_url",
            "title": "Paper URL",
            "url": "https://example.com/paper",
            "scenario": "shared",
            "source_type": "webpage",
        },
    )

    assert registered.status_code == 200
    assert registered.json()["material"]["url"] == "https://example.com/paper"

    listing = client.get("/api/kg/materials")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["status"] == "ok"
    assert payload["count"] == 2
    assert {material["material_id"] for material in payload["materials"]} == {
        "manual_note",
        "paper_url",
    }


def test_kg_material_extract_route_returns_document_understanding_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extraction API should expose document map and prompt-context artifacts."""
    monkeypatch.setattr(
        service_kg_materials,
        "DEFAULT_SOURCE_KG_MATERIAL_DIR",
        tmp_path / "materials",
    )
    client = TestClient(app)

    upload = client.post(
        "/api/kg/materials/upload",
        files={
            "file": (
                "mapped_note.txt",
                (
                    "# Pump Section\n"
                    "Condition Monitoring (CM) observes Pump cavitation. "
                    "Pump cavitation indicates seal wear."
                ),
                "text/plain",
            )
        },
        data={
            "title": "Mapped note",
            "scenario": "tep",
            "source_type": "text",
            "material_id": "mapped_note",
        },
    )
    assert upload.status_code == 200

    response = client.post(
        "/api/kg/materials/mapped_note/extract",
        json={
            "provider": "offline_fixture",
            "document_understanding_mode": "long_context",
            "overwrite": True,
            "document_ie_payload": {
                "entities": [
                    {
                        "id": "PumpCavitation",
                        "name": "Pump cavitation",
                        "label": "FaultEvent",
                        "evidence": "Pump cavitation",
                    },
                    {
                        "id": "SealWear",
                        "name": "Seal wear",
                        "label": "RootCause",
                        "evidence": "seal wear",
                    },
                ],
                "relations": [
                    {
                        "head": "PumpCavitation",
                        "relation": "SUGGESTS_ROOT_CAUSE",
                        "tail": "SealWear",
                        "evidence": "Pump cavitation indicates seal wear.",
                        "confidence": 0.55,
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "extracted"
    assert payload["document_understanding_map_path"]
    assert payload["chunk_prompt_context_path"]
    assert payload["material"]["extraction"]["document_understanding_map_path"] == (
        payload["document_understanding_map_path"]
    )
    assert payload["material"]["extraction"]["chunk_prompt_context_path"] == (
        payload["chunk_prompt_context_path"]
    )
    assert Path(payload["document_understanding_map_path"]).is_file()
    assert Path(payload["chunk_prompt_context_path"]).is_file()


def test_kg_material_build_sources_feed_existing_construction_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selected extracted materials should run through the existing KG builder."""
    material_root = tmp_path / "materials"
    build_root = tmp_path / "builds"
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "PumpFault",
                        "name": "Pump fault",
                        "label": "FaultEvent",
                        "scenario": "tep",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.62,
                    }
                ),
                json.dumps(
                    {
                        "id": "SealWear",
                        "name": "Seal wear",
                        "label": "RootCause",
                        "scenario": "tep",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.62,
                    }
                ),
                json.dumps(
                    {
                        "head": "PumpFault",
                        "relation": "SUGGESTS_ROOT_CAUSE",
                        "tail": "SealWear",
                        "scenario": "tep",
                        "source": "pump_manual",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.55,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        service_kg_materials,
        "DEFAULT_SOURCE_KG_MATERIAL_DIR",
        material_root,
    )
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        build_root,
    )
    service_kg_materials.register_kg_material(
        service_kg_materials.KGMaterialRegisterRequest(
            material_id="pump_manual",
            title="Pump manual",
            source_uri=str(tmp_path / "pump_manual.txt"),
            source_kind="local_path",
            scenario="tep",
            material_type="text",
            extraction=service_kg_materials.KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_id="pump_manual",
                record_count=3,
            ),
        )
    )
    client = TestClient(app)

    sources_response = client.post(
        "/api/kg/materials/build-sources",
        json={
            "material_ids": ["pump_manual"],
            "output_name": "pump_manual_build",
            "overwrite": True,
            "run_id": "kgbuild_pump_manual",
        },
    )

    assert sources_response.status_code == 200
    construction_request = sources_response.json()["construction_request"]
    build_response = client.post("/api/kg/construction/build", json=construction_request)

    assert build_response.status_code == 200
    build_payload = build_response.json()
    assert build_payload["run_id"] == "kgbuild_pump_manual"
    assert Path(build_payload["nodes_path"]).is_file()
    assert Path(build_payload["edges_path"]).is_file()
    assert build_payload["summary"]["edge_count"] == 1


def test_kg_material_direct_build_runs_material_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct material build route should emit artifact-complete build payloads."""
    material_root = tmp_path / "materials"
    build_root = tmp_path / "builds"
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "PumpFault",
                        "name": "Pump fault",
                        "label": "FaultEvent",
                        "scenario": "tep",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.62,
                    }
                ),
                json.dumps(
                    {
                        "id": "SealWear",
                        "name": "Seal wear",
                        "label": "RootCause",
                        "scenario": "tep",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.62,
                    }
                ),
                json.dumps(
                    {
                        "head": "PumpFault",
                        "relation": "SUGGESTS_ROOT_CAUSE",
                        "tail": "SealWear",
                        "scenario": "tep",
                        "source": "pump_manual",
                        "evidence": "Pump fault can indicate seal wear.",
                        "confidence": 0.55,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        service_kg_materials,
        "DEFAULT_SOURCE_KG_MATERIAL_DIR",
        material_root,
    )
    monkeypatch.setattr(
        service_kg_construction,
        "DEFAULT_SOURCE_KG_BUILD_DIR",
        build_root,
    )
    service_kg_materials.register_kg_material(
        service_kg_materials.KGMaterialRegisterRequest(
            material_id="pump_manual",
            title="Pump manual",
            source_uri=str(tmp_path / "pump_manual.txt"),
            source_kind="local_path",
            scenario="tep",
            material_type="text",
            extraction=service_kg_materials.KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_id="pump_manual",
                record_count=3,
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/kg/materials/build",
        json={
            "material_ids": ["pump_manual"],
            "output_name": "pump_manual_direct",
            "overwrite": True,
            "run_id": "kgbuild_pump_manual_direct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "kgbuild_pump_manual_direct"
    assert Path(payload["nodes_path"]).is_file()
    assert Path(payload["edges_path"]).is_file()
    assert Path(payload["review_queue_path"]).is_file()
    assert Path(payload["publish_report_path"]).is_file()
    assert Path(payload["diff_path"]).is_file()
    assert payload["summary"]["edge_count"] == 1
    assert payload["summary"]["material_library"]["material_ids"] == ["pump_manual"]
    assert payload["material_ids"] == ["pump_manual"]
    assert Path(payload["source_library_manifest_path"]).is_file()
    assert Path(payload["alignment_manifest_path"]).is_file()
    assert Path(payload["published_nodes_path"]).is_file()
    assert Path(payload["published_edges_path"]).is_file()
    assert Path(payload["document_understanding_manifest_path"]).is_file()
    assert Path(payload["document_map_path"]).is_file()
    assert Path(payload["chunk_prompt_context_path"]).is_file()
    assert Path(payload["cross_chunk_proposals_path"]).is_file()
    assert Path(payload["publish_manifest_path"]).is_file()
    assert payload["artifacts"]["alignment_manifest"] == payload["alignment_manifest_path"]
    assert payload["artifacts"]["document_map"] == payload["document_map_path"]
    assert payload["artifacts"]["cross_chunk_proposals"] == (
        payload["cross_chunk_proposals_path"]
    )
    assert payload["artifacts"]["kg_construction_diff"] == payload["diff_path"]
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["material_library"]["extraction_mode"] == "never"

    artifact_response = client.get(
        "/api/kg/construction/builds/kgbuild_pump_manual_direct/artifacts/"
        "kg_construction_diff"
    )

    assert artifact_response.status_code == 200
    assert artifact_response.json()["artifact_type"] == "kg_construction_diff_v1"


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
