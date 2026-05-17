"""Smoke the RootLens dashboard API contract used by the Vite client."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from kgtracevis.service import api as service_api
from kgtracevis.service import handlers as service_handlers
from kgtracevis.service import kg_drafts as service_kg_drafts
from kgtracevis.service import kg_materials as service_kg_materials
from kgtracevis.service import runs as service_runs

DEFAULT_EXAMPLE = Path("data/examples/records/mvtec_records.jsonl")


def main() -> None:
    """Run the local dashboard smoke path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--example",
        type=Path,
        default=DEFAULT_EXAMPLE,
        help="Producer-record file to upload through /api/runs/upload.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Path-ranking depth submitted with the upload.",
    )
    parser.add_argument(
        "--persist-runs",
        type=Path,
        default=None,
        help="Optional artifact directory. By default, temporary smoke artifacts are removed.",
    )
    args = parser.parse_args()

    if args.persist_runs is not None:
        _run_smoke(
            args.example,
            run_dir=args.persist_runs,
            draft_path=args.persist_runs / "kg_drafts.jsonl",
            top_k=args.top_k,
        )
        return

    with TemporaryDirectory(prefix="rootlens-dashboard-smoke-") as temp_dir:
        temp_path = Path(temp_dir)
        _run_smoke(
            args.example,
            run_dir=temp_path / "runs",
            draft_path=temp_path / "kg_drafts.jsonl",
            top_k=args.top_k,
        )


class _SmokeIEClient:
    def extract_candidates(self, chunk, *, prompt: str, response_schema: dict[str, object]) -> dict[str, object]:
        del prompt, response_schema
        return {
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
                    "evidence": chunk.text,
                    "confidence": 0.55,
                }
            ],
        }


class _SmokeFeedbackStore:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record_feedback(self, request: service_handlers.FeedbackRequest) -> dict[str, object]:
        target_id = request.target_id or request.case_id or request.run_id or request.target_type
        metadata = dict(request.metadata or {})
        record = {
            "feedback_id": f"feedback-{len(self.records) + 1}",
            "created_at": "2026-05-16T00:00:00+00:00",
            "run_id": request.run_id,
            "case_id": request.case_id,
            "target_type": request.target_type,
            "target_id": target_id,
            "target_key": str(metadata.get("target_key") or f"{request.target_type}:{target_id}"),
            "action": request.review_action(),
            "note": request.review_note(),
            "reviewer": request.reviewer,
            "source": request.source or "rootlens-dashboard-smoke",
            "metadata": metadata or None,
        }
        self.records.insert(0, record)
        return {"status": "recorded", "record": record}

    def list_feedback(self, request: service_handlers.ReviewLedgerListRequest) -> dict[str, object]:
        filtered = [
            record
            for record in self.records
            if (request.run_id is None or record.get("run_id") == request.run_id)
            and (request.case_id is None or record.get("case_id") == request.case_id)
            and (request.target_type is None or record.get("target_type") == request.target_type)
            and (request.target_id is None or record.get("target_id") == request.target_id)
        ]
        paged = filtered[request.offset : request.offset + request.limit]
        return {
            "records": paged,
            "total_count": len(filtered),
            "returned_count": len(paged),
            "offset": request.offset,
            "limit": request.limit,
            "claim_boundary": "candidate/plausible explanation only; not a verified root-cause label",
        }


def _run_smoke(
    example_path: Path,
    *,
    run_dir: Path,
    draft_path: Path,
    top_k: int,
) -> None:
    if not example_path.is_file():
        raise FileNotFoundError(f"example upload file not found: {example_path}")
    if top_k < 1:
        raise ValueError("--top-k must be >= 1")

    run_dir.mkdir(parents=True, exist_ok=True)
    service_runs.DEFAULT_RUNS_DIR = run_dir
    material_root = run_dir / "materials"
    service_kg_materials.DEFAULT_SOURCE_KG_MATERIAL_DIR = material_root
    service_kg_materials.configure_material_store_for_testing(
        service_kg_materials.FileKGMaterialStore(material_root)
    )

    def record_kg_draft_to_smoke_path(
        request: service_kg_drafts.KGDraftRequest,
    ) -> dict[str, object]:
        return service_kg_drafts.record_kg_draft(request, output_path=draft_path)

    def list_kg_drafts_from_smoke_path(
        request: service_kg_drafts.KGDraftListRequest,
    ) -> service_kg_drafts.KGDraftListResponse:
        return service_kg_drafts.list_kg_drafts(request, input_path=draft_path)

    def extract_material_with_smoke_ie(
        material_id: str,
        request: service_kg_materials.KGMaterialExtractionRunRequest | None = None,
    ) -> service_kg_materials.KGMaterialExtractionRunResponse:
        return service_kg_materials.extract_kg_material_to_structured_records(
            material_id,
            request or service_kg_materials.KGMaterialExtractionRunRequest(),
            client=_SmokeIEClient(),
        )

    service_api.record_kg_draft = record_kg_draft_to_smoke_path
    service_api.list_kg_drafts = list_kg_drafts_from_smoke_path
    service_api.extract_kg_material_to_structured_records = extract_material_with_smoke_ie
    feedback_store = _SmokeFeedbackStore()
    service_handlers._default_feedback_store = lambda: feedback_store

    client = TestClient(service_api.create_app())
    _require(client.get("/api/health").json()["status"] == "ok", "health route failed")

    bootstrap = client.get("/api/dashboard/bootstrap")
    _require(bootstrap.status_code == 200, "bootstrap route failed")
    bootstrap_payload = bootstrap.json()
    _require(bootstrap_payload["status"] == "ok", "bootstrap did not return ok status")
    _require(
        {"records", "evidence", "image"}
        == {mode["mode"] for mode in bootstrap_payload["upload_modes"]},
        "bootstrap upload modes are incomplete",
    )
    kg_studio = client.get("/api/kg/studio")
    _require(kg_studio.status_code == 200, "KG Studio route failed")
    kg_studio_payload = kg_studio.json()
    _require(
        kg_studio_payload["status"] in {"ok", "empty"},
        "KG Studio returned an unsupported status",
    )
    if kg_studio_payload["status"] == "ok":
        _require(kg_studio_payload["edge_count"] > 0, "KG Studio returned no edges")
        _require(
            len(kg_studio_payload["review_targets"]) > 0,
            "KG Studio returned no review targets",
        )
        kg_target = kg_studio_payload["review_targets"][0]
        kg_draft = client.post(
            "/api/kg/drafts",
            json={
                "target_type": "edge",
                "target_id": kg_target["target_id"],
                "target_key": kg_target["target_key"],
                "draft_action": "revise",
                "proposed_confidence": 0.5,
                "note": "dashboard smoke KG draft",
                "source": "rootlens-dashboard-smoke",
            },
        )
        _require(kg_draft.status_code == 200, f"KG draft submit failed: {kg_draft.text}")
        _require(kg_draft.json()["status"] == "recorded", "KG draft was not recorded")
        _require(draft_path.is_file(), "KG draft JSONL was not written")
        kg_draft_history = client.get(
            "/api/kg/drafts",
            params={"target_key": kg_target["target_key"], "limit": 20},
        )
        _require(kg_draft_history.status_code == 200, f"KG draft history failed: {kg_draft_history.text}")
        _require(
            kg_draft_history.json()["returned_count"] >= 1,
            "KG draft history returned no records",
        )
    source_draft = client.post(
        "/api/kg/source-draft",
        json={
            "source_id": "smoke_source",
            "source_text": (
                "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,"
                "MechanicalContact,mvtec,smoke evidence"
            ),
            "provider": "heuristic",
            "default_scenario": "mvtec",
            "confidence": 0.55,
        },
    )
    _require(
        source_draft.status_code == 200,
        f"source-to-KG draft failed: {source_draft.text}",
    )
    _require(
        len(source_draft.json()["candidate_edges"]) == 1,
        "source-to-KG draft returned no candidates",
    )
    _require(
        client.get("/api/kg/drafts").json()["total_count"] >= 1,
        "source-to-KG preview should not clear persisted KG drafts",
    )

    material_upload = client.post(
        "/api/kg/materials/upload",
        files={"file": ("pump_note.txt", "Pump cavitation indicates seal wear.", "text/plain")},
        data={
            "title": "Pump note",
            "scenario": "tep",
            "source_type": "text",
            "material_id": "pump_note",
        },
    )
    _require(material_upload.status_code == 200, f"material upload failed: {material_upload.text}")
    material_extract = client.post(
        "/api/kg/materials/pump_note/extract",
        json={"overwrite": True},
    )
    _require(material_extract.status_code == 200, f"material extract failed: {material_extract.text}")
    chunks = client.get("/api/kg/materials/pump_note/chunks")
    extraction_runs = client.get("/api/kg/materials/pump_note/extractions")
    extraction_artifacts = client.get("/api/kg/materials/pump_note/artifacts")
    _require(chunks.status_code == 200, f"material chunks failed: {chunks.text}")
    _require(extraction_runs.status_code == 200, f"material extraction runs failed: {extraction_runs.text}")
    _require(extraction_artifacts.status_code == 200, f"material artifacts failed: {extraction_artifacts.text}")
    _require(chunks.json()["count"] >= 1, "material chunks returned no records")
    _require(extraction_runs.json()["count"] >= 1, "material extraction runs returned no records")
    _require(extraction_artifacts.json()["count"] >= 1, "material extraction artifacts returned no records")
    build_sources = client.post(
        "/api/kg/materials/build-sources",
        json={"material_ids": ["pump_note"], "output_name": "smoke_material_build", "overwrite": True},
    )
    _require(build_sources.status_code == 200, f"material build-sources failed: {build_sources.text}")
    _require(
        len(build_sources.json()["sources"]) == 1,
        "material build-sources returned no construction inputs",
    )

    with example_path.open("rb") as handle:
        upload = client.post(
            "/api/runs/upload",
            data={"mode": "records", "top_k": str(top_k)},
            files={"file": (example_path.name, handle, "application/jsonl")},
        )
    _require(upload.status_code == 200, f"upload failed: {upload.text}")
    run_detail = upload.json()
    run_id = run_detail["run"]["run_id"]
    _require(run_detail["run"]["case_count"] > 0, "upload created no cases")
    _require(len(run_detail["cases"]) > 0, "upload returned no case rows")
    _require(all(case.get("case_label") for case in run_detail["cases"]), "case rows are missing case labels")
    _require(
        all(isinstance(case.get("generated_evidence"), dict) for case in run_detail["cases"]),
        "case rows are missing generated evidence payloads",
    )
    _require(len(run_detail["workflow_steps"]) > 0, "upload returned no workflow steps")
    _require(len(run_detail["top_k_paths"]) > 0, "upload returned no candidate paths")
    _require("visual_evidence" in run_detail, "upload omitted visual evidence field")
    _require(len(run_detail["path_graph"]["paths"]) > 0, "upload returned no path graph")
    _require(
        len(run_detail["path_graph"]["paths"][0]["edges"]) > 0,
        "first path graph entry has no provenance edges",
    )
    _require(len(run_detail["review_targets"]) > 0, "upload returned no review targets")
    _require(
        all("target_key" in target for target in run_detail["review_targets"]),
        "review targets are missing stable keys",
    )

    runs = client.get("/api/runs")
    _require(runs.status_code == 200, "run history route failed")
    _require(any(run["run_id"] == run_id for run in runs.json()), "new run missing from history")

    detail = client.get(f"/api/runs/{run_id}")
    _require(detail.status_code == 200, "run detail route failed")
    detail_payload = detail.json()
    target = detail_payload["review_targets"][0]
    edge_targets = [
        target
        for target in detail_payload["review_targets"]
        if target["target_type"] == "edge"
    ]
    _require(len(edge_targets) > 0, "run detail returned no edge review targets")
    first_graph_edge = detail_payload["path_graph"]["paths"][0]["edges"][0]
    _require(
        first_graph_edge["target_key"] in {target["target_key"] for target in edge_targets},
        "path graph edge target key does not match review queue",
    )
    feedback = client.post(
        "/api/feedback",
        json={
            "run_id": run_id,
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "action": "needs_review",
            "note": "dashboard smoke review",
            "source": "rootlens-dashboard-smoke",
            "metadata": {"target_key": target["target_key"]},
        },
    )
    _require(feedback.status_code == 200, f"feedback submit failed: {feedback.text}")
    _require(feedback.json()["status"] == "recorded", "feedback was not recorded")
    ledger = client.get(
        "/api/feedback",
        params={"run_id": run_id, "limit": 20},
    )
    _require(ledger.status_code == 200, f"feedback ledger failed: {ledger.text}")
    ledger_payload = ledger.json()
    _require(ledger_payload["returned_count"] >= 1, "feedback ledger returned no records")
    _require(
        any(record.get("target_key") == target["target_key"] for record in ledger_payload["records"]),
        "feedback ledger did not return the submitted target key",
    )

    print(
        "RootLens dashboard smoke passed: "
        f"run_id={run_id}, target_key={target['target_key']}"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
