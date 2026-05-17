"""Smoke the RootLens dashboard API contract used by the Vite client."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from kgtracevis.service import api as service_api
from kgtracevis.service import handlers as service_handlers
from kgtracevis.service import kg_drafts as service_kg_drafts
from kgtracevis.service import runs as service_runs
from kgtracevis.service.handlers import FeedbackRequest, ReviewLedgerListRequest

DEFAULT_EXAMPLE = Path("data/examples/records/mvtec_records.jsonl")


class InMemoryRunStore:
    """Small self-contained run/feedback store for dashboard smoke tests."""

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
            "source": request.source or "rootlens-dashboard-smoke",
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
            offset = int(request.get("offset", 0))
            limit = int(request.get("limit", 50))
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
                "source": record.get("source") or "rootlens-dashboard-smoke",
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
    store = InMemoryRunStore()
    original_feedback_store = service_handlers._default_feedback_store
    service_runs.configure_run_store_for_testing(store)
    service_handlers._default_feedback_store = lambda: store
    service_runs.DEFAULT_RUNS_DIR = run_dir

    def record_kg_draft_to_smoke_path(
        request: service_kg_drafts.KGDraftRequest,
    ) -> dict[str, object]:
        return service_kg_drafts.record_kg_draft(request, output_path=draft_path)

    service_api.record_kg_draft = record_kg_draft_to_smoke_path

    try:
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
        _require(
            bootstrap_payload["reasoning_profile_options"]["mvtec"][0]["profile_id"]
            == "generic_graph_path_default",
            "bootstrap missing mvtec reasoning profile options",
        )
        _require(
            any(
                option["profile_id"] == "tep_root_kgd_default"
                for option in bootstrap_payload["reasoning_profile_options"]["tep"]
            ),
            "bootstrap missing TEP reasoning profile options",
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

        with example_path.open("rb") as handle:
            upload = client.post(
                "/api/runs/upload",
                data={
                    "mode": "records",
                    "dataset": "mvtec",
                    "reasoning_profile_id": "generic_graph_path_default",
                    "top_k": str(top_k),
                },
                files={"file": (example_path.name, handle, "application/jsonl")},
            )
        _require(upload.status_code == 200, f"upload failed: {upload.text}")
        run_detail = upload.json()
        run_id = run_detail["run"]["run_id"]
        _require(run_detail["run"]["case_count"] > 0, "upload created no cases")
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
        _require(
            run_detail["summary"]["pipeline"]["reasoning_profile_id"]
            == "generic_graph_path_default",
            "upload summary omitted reasoning profile id",
        )
        _require(
            run_detail["summary"]["pipeline"]["selection_mode"] == "explicit",
            "upload summary did not preserve explicit reasoning selection",
        )
        _require(
            run_detail["cases"][0]["reasoning_metadata"]["reasoning_profile_id"]
            == "generic_graph_path_default",
            "case reasoning metadata omitted explicit profile",
        )

        runs = client.get("/api/runs")
        _require(runs.status_code == 200, "run history route failed")
        _require(any(run["run_id"] == run_id for run in runs.json()), "new run missing from history")

        detail = client.get(f"/api/runs/{run_id}")
        _require(detail.status_code == 200, "run detail route failed")
        detail_payload = detail.json()
        _require(
            detail_payload["summary"]["pipeline"]["reasoning_profile_id"]
            == "generic_graph_path_default",
            "persisted run detail lost summary.pipeline reasoning profile",
        )
        _require(
            detail_payload["cases"][0]["reasoning_metadata"]["selection_mode"] == "explicit",
            "persisted run detail lost case reasoning metadata",
        )
        _require(
            detail_payload["analysis"] is None
            or detail_payload["analysis"].get("reasoning_metadata") is not None,
            "persisted run detail lost analysis reasoning metadata",
        )
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

        print(
            "RootLens dashboard smoke passed: "
            f"run_id={run_id}, target_key={target['target_key']}"
        )
    finally:
        service_runs.configure_run_store_for_testing(None)
        service_handlers._default_feedback_store = original_feedback_store


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
