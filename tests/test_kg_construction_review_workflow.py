"""Tests for artifact-level KG construction review workflow and CLI."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.workflows.kg_construction_review import (
    ReviewKGConstructionEdgeConfig,
    review_kg_construction_edge_artifact,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)


def test_review_workflow_accepts_edge_and_refreshes_publish_snapshot(
    tmp_path: Path,
) -> None:
    """Artifact review workflow should update decisions, queue, and publish files."""
    build = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=tmp_path / "candidate",
            sources=(
                KGConstructionSource(
                    source_id="review_doc",
                    source_type="txt",
                    scenario="shared",
                    text=_document_text(),
                    metadata={
                        "source_format": "txt",
                        "document_ie_payload": _document_payload(),
                    },
                ),
            ),
            run_id="kgbuild_review_workflow",
        )
    )
    target_key = "CoolingAlert|SUGGESTS_ROOT_CAUSE|PumpSealWear|shared"

    result = review_kg_construction_edge_artifact(
        ReviewKGConstructionEdgeConfig(
            output_dir=build.output_dir,
            action="accept",
            target_key=target_key,
            reviewer="unit-test",
            note="accepted for workflow test",
        )
    )

    decisions = [
        json.loads(line)
        for line in result.review_decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    published_edges = _read_csv_rows(result.published_edges_path)
    publish_report = json.loads(result.publish_report_path.read_text(encoding="utf-8"))
    review_queue = json.loads(build.review_queue_path.read_text(encoding="utf-8"))

    assert result.edge["review_status"] == "reviewed"
    assert result.summary["review_status_counts"] == {"reviewed": 1}
    assert decisions[0]["action"] == "accept"
    assert decisions[0]["target_key"] == target_key
    assert published_edges[0]["review_status"] == "reviewed"
    assert published_edges[0]["kg_build_id"] == "kgbuild_review_workflow"
    assert publish_report["disposition_counts"] == {"accepted": 1}
    assert review_queue[0]["review_status"] == "reviewed"


def test_review_source_kg_cli_accepts_offline_document_edge(
    tmp_path: Path,
) -> None:
    """CLI should provide a no-service human review path for build artifacts."""
    output_dir = tmp_path / "cli_candidate"
    build = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_kg.py",
            "--toy-generic-document-source",
            "--run-id",
            "kgbuild_cli_review",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "source_to_kg_construction_result_v1" in build.stdout

    review = subprocess.run(
        [
            sys.executable,
            "scripts/review_source_kg.py",
            "--build-dir",
            str(output_dir),
            "--action",
            "accept",
            "--target-key",
            "CoolingAlert|SUGGESTS_ROOT_CAUSE|PumpSealWear|shared",
            "--reviewer",
            "unit-test",
            "--note",
            "accepted by CLI smoke",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(review.stdout)
    published_edges = _read_csv_rows(output_dir / "published_edges.csv")
    publish_report = json.loads((output_dir / "publish_report.json").read_text())

    assert payload["action"] == "accept"
    assert payload["edge_review_status"] == "reviewed"
    assert published_edges[0]["review_status"] == "reviewed"
    assert published_edges[0]["kg_build_id"] == "kgbuild_cli_review"
    assert publish_report["disposition_counts"] == {"accepted": 1}


def _document_text() -> str:
    return "Cooling alert can suggest pump seal wear."


def _document_payload() -> dict[str, object]:
    return {
        "entities": [
            {
                "id": "CoolingAlert",
                "name": "Cooling alert",
                "label": "Event",
                "evidence": "Cooling alert can suggest pump seal wear.",
            },
            {
                "id": "PumpSealWear",
                "name": "Pump seal wear",
                "label": "RootCause",
                "evidence": "pump seal wear",
            },
        ],
        "relations": [
            {
                "head": "CoolingAlert",
                "relation": "SUGGESTS_ROOT_CAUSE",
                "tail": "PumpSealWear",
                "evidence": "Cooling alert can suggest pump seal wear.",
            }
        ],
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
