"""Smoke the RootLens dashboard API contract used by the Vite client."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from kgtracevis.service import api as service_api
from kgtracevis.service import handlers as service_handlers
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
        help="Optional run directory. By default, temporary smoke artifacts are removed.",
    )
    parser.add_argument(
        "--feedback-path",
        type=Path,
        default=None,
        help="Optional feedback JSONL path. Defaults to the smoke artifact directory.",
    )
    args = parser.parse_args()

    if args.persist_runs is not None:
        feedback_path = args.feedback_path or args.persist_runs / "feedback.jsonl"
        _run_smoke(
            args.example,
            run_dir=args.persist_runs,
            feedback_path=feedback_path,
            top_k=args.top_k,
        )
        return

    with TemporaryDirectory(prefix="rootlens-dashboard-smoke-") as temp_dir:
        temp_path = Path(temp_dir)
        _run_smoke(
            args.example,
            run_dir=temp_path / "runs",
            feedback_path=args.feedback_path or temp_path / "feedback.jsonl",
            top_k=args.top_k,
        )


def _run_smoke(example_path: Path, *, run_dir: Path, feedback_path: Path, top_k: int) -> None:
    if not example_path.is_file():
        raise FileNotFoundError(f"example upload file not found: {example_path}")
    if top_k < 1:
        raise ValueError("--top-k must be >= 1")

    run_dir.mkdir(parents=True, exist_ok=True)
    service_runs.DEFAULT_RUNS_DIR = run_dir
    service_runs.LEGACY_WEB_RUNS_DIR = run_dir / "legacy"

    def record_feedback_to_smoke_path(
        request: service_handlers.FeedbackRequest,
    ) -> dict[str, Any]:
        return service_handlers.record_feedback(request, output_path=feedback_path)

    service_api.record_feedback = record_feedback_to_smoke_path

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
    _require(len(run_detail["workflow_steps"]) > 0, "upload returned no workflow steps")
    _require(len(run_detail["top_k_paths"]) > 0, "upload returned no candidate paths")
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
    _require(feedback_path.is_file(), "feedback JSONL was not written")

    print(
        "RootLens dashboard smoke passed: "
        f"run_id={run_id}, target_key={target['target_key']}, feedback_path={feedback_path}"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
