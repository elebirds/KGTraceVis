"""Tests for asynchronous KG construction progress reporting."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from kgtracevis.service import kg_construction
from kgtracevis.service.api import app
from kgtracevis.service.kg_construction import (
    KGConstructionBuildRequest,
    KGConstructionSourceInput,
    get_kg_construction_build_job,
    submit_kg_construction_build_job,
)
from kgtracevis.source_kg_compiler.models import SourceKGArtifactPaths
from kgtracevis.source_kg_compiler.workflow import SourceKGCompilerResult


def test_submit_kg_construction_build_job_records_progress(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Background source KG builds should expose pollable compiler progress."""
    monkeypatch.setattr(
        kg_construction,
        "run_source_kg_compiler_workflow",
        _fake_compiler_workflow,
    )

    response = submit_kg_construction_build_job(
        KGConstructionBuildRequest(
            run_id="progress_unit",
            output_name="progress_unit",
            overwrite=True,
            sources=[
                KGConstructionSourceInput(
                    source_id="inline_source",
                    scenario="mvtec",
                    source_text="SCENARIO: mvtec\nScratch implies contact.",
                )
            ],
        ),
        build_root=tmp_path,
    )

    assert response.status in {"queued", "running", "succeeded"}
    finished = _wait_for_job("progress_unit", tmp_path)
    assert finished.status == "succeeded"
    assert finished.result is not None
    assert finished.progress_event_count >= 2
    assert finished.last_event is not None
    assert finished.last_event["event"] == "job_succeeded"
    assert Path(finished.progress_path).is_file()

    incremental = get_kg_construction_build_job(
        "progress_unit",
        build_root=tmp_path,
        after_sequence=1,
    )
    assert incremental.events
    assert all(int(event["sequence"]) > 1 for event in incremental.events)


def test_kg_construction_build_job_api_returns_progress(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """The FastAPI job endpoints should submit and poll build progress."""
    monkeypatch.setattr(kg_construction, "DEFAULT_SOURCE_KG_BUILD_DIR", tmp_path)
    monkeypatch.setattr(
        kg_construction,
        "run_source_kg_compiler_workflow",
        _fake_compiler_workflow,
    )
    client = TestClient(app)

    submitted = client.post(
        "/api/kg/construction/build-jobs",
        json={
            "run_id": "api_progress_unit",
            "output_name": "api_progress_unit",
            "overwrite": True,
            "sources": [
                {
                    "source_id": "api_source",
                    "scenario": "wafer",
                    "source_text": "SCENARIO: wafer\nLoc pattern source.",
                }
            ],
        },
    )

    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    payload = _wait_for_api_job(client, job_id)
    assert payload["status"] == "succeeded"
    assert payload["progress_event_count"] >= 2
    assert payload["result"]["summary"]["status"] == "built"

    incremental = client.get(
        f"/api/kg/construction/build-jobs/{job_id}",
        params={"after_sequence": 1},
    )
    assert incremental.status_code == 200
    assert incremental.json()["events"]


def _wait_for_job(job_id: str, build_root: Path):
    deadline = time.time() + 5
    while time.time() < deadline:
        job = get_kg_construction_build_job(job_id, build_root=build_root)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_api_job(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.time() + 5
    while time.time() < deadline:
        response = client.get(f"/api/kg/construction/build-jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job_id}")


def _fake_compiler_workflow(config: Any) -> SourceKGCompilerResult:
    if config.progress_callback is not None:
        config.progress_callback(
            {
                "stage": "knowledge_cards",
                "event": "llm_start",
                "item": "unit:1",
                "elapsed_seconds": 0.0,
            }
        )
    paths = _write_fake_artifacts(config.output_dir)
    if config.progress_callback is not None:
        config.progress_callback(
            {
                "stage": "compile_finish",
                "event": "stage_finish",
                "entities": 1,
                "edges": 1,
                "elapsed_seconds": 0.01,
            }
        )
    summary = {
        "artifact_type": "source_kg_compiler_summary_v1",
        "output_dir": paths.output_dir.as_posix(),
        "counts": {
            "source_units": 1,
            "knowledge_cards": 1,
            "entities": 1,
            "edges": 1,
        },
        "qa_status": "passed",
        "validation_status": "passed",
        "strict_generated_only": True,
        "artifacts": {
            "source_units": paths.source_units.as_posix(),
            "knowledge_cards": paths.knowledge_cards.as_posix(),
            "entities": paths.entities.as_posix(),
            "edges": paths.edges.as_posix(),
            "nodes_csv": paths.nodes_csv.as_posix(),
            "edges_csv": paths.edges_csv.as_posix(),
            "qa_report": paths.qa_report.as_posix(),
            "validation_report": paths.validation_report.as_posix(),
            "domain_profiles": paths.domain_profiles.as_posix(),
            "domain_profile_report": paths.domain_profile_report.as_posix(),
            "domain_profiles_manifest": paths.domain_profiles_manifest.as_posix(),
            "runtime_views_manifest": paths.runtime_views_manifest.as_posix(),
        },
    }
    return SourceKGCompilerResult(
        output_dir=paths.output_dir,
        artifact_paths=paths,
        summary=summary,
        qa_report={"status": "passed"},
        validation_report={"status": "passed", "strict_generated_only": True},
    )


def _write_fake_artifacts(output_dir: Path) -> SourceKGArtifactPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = SourceKGArtifactPaths(
        output_dir=output_dir,
        source_units=output_dir / "source_units.jsonl",
        knowledge_cards=output_dir / "knowledge_cards.jsonl",
        entities=output_dir / "entities.jsonl",
        edges=output_dir / "edges.jsonl",
        nodes_csv=output_dir / "nodes.csv",
        edges_csv=output_dir / "edges.csv",
        qa_report=output_dir / "qa_report.json",
        validation_report=output_dir / "validation_report.json",
        domain_profiles=output_dir / "domain_profiles.json",
        domain_profile_report=output_dir / "domain_profile_report.json",
        domain_profiles_manifest=output_dir / "domain_profiles_manifest.json",
        runtime_views_manifest=output_dir / "runtime_views_manifest.json",
    )
    paths.nodes_csv.write_text(
        "id,name,label,scenario,aliases,description\n"
        "ScratchDefect,Scratch defect,AnomalyType,mvtec,scratch,Test node\n",
        encoding="utf-8",
    )
    paths.edges_csv.write_text(
        "head,relation,tail,scenario,source,evidence,confidence,weight,"
        "review_status,feedback_count,accepted_count,rejected_count\n"
        "ScratchDefect,HAS_PLAUSIBLE_CAUSE,ScratchDefect,mvtec,test,evidence,"
        "0.8,0.2,auto,0,0,0\n",
        encoding="utf-8",
    )
    for path in (
        paths.source_units,
        paths.knowledge_cards,
        paths.entities,
        paths.edges,
    ):
        path.write_text("{}\n", encoding="utf-8")
    for path in (
        paths.qa_report,
        paths.validation_report,
        paths.domain_profiles,
        paths.domain_profile_report,
        paths.domain_profiles_manifest,
        paths.runtime_views_manifest,
    ):
        path.write_text("{}", encoding="utf-8")
    return paths
