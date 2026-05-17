"""Tests for candidate KG overlay validation workflow and CLI."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from kgtracevis.workflows.kg_overlay_validation import (
    KGOverlayValidationConfig,
    run_kg_overlay_validation,
)


def test_kg_overlay_validation_writes_runtime_and_import_report(
    tmp_path: Path,
) -> None:
    """Candidate overlays should be validated against runtime RCA and import dry-run."""
    build_dir = _write_build_dir(tmp_path)
    example_dir = _write_example_dir(tmp_path)

    result = run_kg_overlay_validation(
        KGOverlayValidationConfig(build_dir=build_dir, example_dir=example_dir)
    )

    assert result.output_path == build_dir / "kg_overlay_validation_report.json"
    assert result.output_path.is_file()
    report = result.report
    assert report["artifact_type"] == "kg_overlay_validation_report_v1"
    assert report["kg_backend"] == "explicit_seed_overlay"
    assert report["contract_validated"] is True
    assert report["runtime_validated"] is True
    assert report["overlay_contributed"] is True
    assert report["overlay_contribution_case_count"] == 1
    assert report["overlay_contribution_kg_build_ids"] == [
        "kgbuild_overlay_validation"
    ]
    assert report["overlay_contribution_source_edge_ids"] == [
        "OverlayCoolingAlert|CAUSES|OverlaySealWear|shared"
    ]
    assert report["missing_overlay_contribution_warning"] == ""
    assert report["validated"] is True
    assert report["example_count"] == 1
    assert report["runtime_graph"]["include_defaults"] is True
    assert report["import_dry_run"]["dry_run"] is True
    assert report["import_dry_run"]["include_defaults"] is True
    assert report["import_dry_run"]["node_count"] >= 2
    example = report["examples"][0]
    assert example["case_id"] == "overlay_case_001"
    assert example["top_k_path_count"] >= 1
    assert example["top_target_entity_id"] == "OverlaySealWear"
    assert example["kg_build_ids"] == ["kgbuild_overlay_validation"]
    assert example["overlay_contributed"] is True
    assert example["overlay_contribution_kg_build_ids"] == [
        "kgbuild_overlay_validation"
    ]
    assert example["overlay_contribution_source_edge_ids"] == [
        "OverlayCoolingAlert|CAUSES|OverlaySealWear|shared"
    ]
    assert example["path_strengths"] == [0.77]
    assert example["rca_scores"] == [0.77]
    assert example["source_edge_ids"] == [
        "OverlayCoolingAlert|CAUSES|OverlaySealWear|shared"
    ]


def test_validate_kg_overlay_cli_accepts_build_dir(tmp_path: Path) -> None:
    """The script should remain a thin client over the reusable workflow."""
    build_dir = _write_build_dir(tmp_path)
    example_dir = _write_example_dir(tmp_path)
    output_path = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_kg_overlay.py",
            "--build-dir",
            str(build_dir),
            "--example-dir",
            str(example_dir),
            "--output-path",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    saved_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == saved_payload
    assert payload["kg_node_paths"] == [str(build_dir / "nodes.csv")]
    assert payload["kg_edge_paths"] == [str(build_dir / "edges.csv")]
    assert payload["contract_validated"] is True
    assert payload["runtime_validated"] is True
    assert payload["overlay_contributed"] is True
    assert payload["runtime_graph"]["include_defaults"] is True
    assert payload["examples"][0]["kg_build_ids"] == ["kgbuild_overlay_validation"]


def test_validate_kg_overlay_cli_supports_overlay_only_runtime(
    tmp_path: Path,
) -> None:
    """TEP-style overlays can be runtime validated without merging default seeds."""
    build_dir = _write_build_dir(tmp_path)
    example_dir = _write_example_dir(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_kg_overlay.py",
            "--build-dir",
            str(build_dir),
            "--example-dir",
            str(example_dir),
            "--overlay-only-runtime",
            "--overlay-only-import",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["runtime_graph"]["include_defaults"] is False
    assert payload["import_dry_run"]["include_defaults"] is False
    assert payload["overlay_contributed"] is True


def test_kg_overlay_validation_distinguishes_loading_from_contribution(
    tmp_path: Path,
) -> None:
    """Loading/import success should not imply that examples used the overlay."""
    build_dir = _write_build_dir(tmp_path)
    example_dir = _write_non_contributing_example_dir(tmp_path)

    result = run_kg_overlay_validation(
        KGOverlayValidationConfig(build_dir=build_dir, example_dir=example_dir)
    )

    report = result.report
    assert report["contract_validated"] is True
    assert report["runtime_validated"] is True
    assert report["overlay_contributed"] is False
    assert report["overlay_contribution_case_count"] == 0
    assert report["overlay_contribution_kg_build_ids"] == []
    assert report["overlay_contribution_source_edge_ids"] == []
    assert report["missing_overlay_contribution_warning"].startswith(
        "Candidate overlay loaded and runtime examples executed"
    )
    assert report["validated"] is False
    assert report["examples"][0]["overlay_contributed"] is False


def _write_build_dir(tmp_path: Path) -> Path:
    build_dir = tmp_path / "candidate_build"
    build_dir.mkdir()
    _write_csv(
        build_dir / "nodes.csv",
        [
            {
                "id": "OverlayCoolingAlert",
                "name": "Overlay cooling alert",
                "label": "FaultType",
                "scenario": "shared",
                "aliases": "overlay cooling alert",
                "description": "Runtime overlay source node",
            },
            {
                "id": "OverlaySealWear",
                "name": "Overlay seal wear",
                "label": "RootCause",
                "scenario": "shared",
                "aliases": "overlay seal wear",
                "description": "Runtime overlay RCA target",
            },
        ],
    )
    _write_csv(
        build_dir / "edges.csv",
        [
            {
                "head": "OverlayCoolingAlert",
                "relation": "CAUSES",
                "tail": "OverlaySealWear",
                "scenario": "shared",
                "source": "overlay_validation_fixture",
                "evidence": "Fixture row links overlay cooling alert to seal wear.",
                "confidence": "0.82",
                "weight": "0.18",
                "review_status": "auto",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
                "relation_family": "CAUSES",
                "propagation_enabled": "true",
                "propagation_direction": "forward",
                "propagation_priority": "1.0",
                "attenuation": "0.9",
                "edge_weight": "0.23",
                "root_candidate": "true",
                "observable": "false",
                "event_anchor": "OverlayCoolingAlert",
                "fault_anchor": "OverlaySealWear",
                "task_view": "overlay_validation",
                "confidence_policy": "min",
                "source_trust": "0.8",
                "rca_score": "0.77",
                "rca_score_confidence": "0.82",
                "rca_score_priority": "1.0",
                "rca_score_attenuation": "0.9",
                "rca_score_source_trust": "0.8",
                "external_edge_id": "fixture_edge_001",
                "kg_build_id": "kgbuild_overlay_validation",
            }
        ],
    )
    return build_dir


def _write_example_dir(tmp_path: Path) -> Path:
    example_dir = tmp_path / "examples"
    example_dir.mkdir()
    payload = {
        "case_id": "overlay_case_001",
        "dataset": "mvtec",
        "source": "unknown",
        "object": "pump",
        "anomaly_type": "Overlay cooling alert",
        "location": None,
        "morphology": None,
        "severity": 0.7,
        "confidence": 0.8,
        "timestamp": None,
        "raw_evidence": {
            "variables": [],
            "variable_contributions": {},
            "log_events": [],
            "description": "Overlay validation fixture.",
        },
        "normalized_evidence": {},
        "kg_analysis": {},
    }
    (example_dir / "overlay_case.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return example_dir


def _write_non_contributing_example_dir(tmp_path: Path) -> Path:
    example_dir = tmp_path / "non_contributing_examples"
    example_dir.mkdir()
    payload = {
        "case_id": "non_contributing_case_001",
        "dataset": "mvtec",
        "source": "unknown",
        "object": "cable",
        "anomaly_type": "scratch",
        "location": None,
        "morphology": None,
        "severity": 0.4,
        "confidence": 0.7,
        "timestamp": None,
        "raw_evidence": {
            "variables": [],
            "variable_contributions": {},
            "log_events": [],
            "description": "Uses default KG paths rather than the overlay fixture.",
        },
        "normalized_evidence": {},
        "kg_analysis": {},
    }
    (example_dir / "non_contributing_case.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return example_dir


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    assert rows
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
