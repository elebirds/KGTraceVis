"""Tests for paper-facing experiment manifest generation."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.experiments.paper_tables import (
    COMMAND_MANIFEST_FILENAME,
    PAPER_MANIFEST_FILENAME,
    SUMMARY_FILENAME,
    build_paper_tables,
)


def test_build_paper_tables_groups_adapter_noise_and_commands(tmp_path: Path) -> None:
    """The builder should group generated outputs without writing into paper/."""
    mvtec_output = run_adapter_pipeline(
        "data/examples/records/mvtec_records.jsonl",
        tmp_path / "runs" / "adapter_pipeline_mvtec",
        dataset="mvtec",
        top_k=2,
    )
    wm811k_output = run_adapter_pipeline(
        "data/examples/records/wm811k_records.jsonl",
        tmp_path / "runs" / "adapter_pipeline_wm811k",
        dataset="wafer",
        top_k=2,
    )
    noise_summary = _write_noise_summary(tmp_path / "runs" / "v0_examples" / "summary.json")
    suite_summary = _write_suite_summary(
        tmp_path / "runs" / "v0_experiment_suite" / "summary.json",
        mvtec_summary=mvtec_output.summary_path,
        wm811k_summary=wm811k_output.summary_path,
        noise_summary=noise_summary,
    )

    output = build_paper_tables(
        output_dir=tmp_path / "artifacts" / "paper_tables_v0",
        adapter_summary_paths=[mvtec_output.summary_path, wm811k_output.summary_path],
        noise_summary_path=noise_summary,
        suite_summary_path=suite_summary,
        overwrite=True,
    )

    expected_output_dir = tmp_path / "artifacts" / "paper_tables_v0"
    assert output.manifest_path == expected_output_dir / PAPER_MANIFEST_FILENAME
    assert output.command_manifest_path == (
        expected_output_dir / COMMAND_MANIFEST_FILENAME
    )
    assert output.summary_path == expected_output_dir / SUMMARY_FILENAME
    assert output.manifest_path.is_file()
    assert output.command_manifest_path.is_file()
    assert output.summary_path.is_file()

    rows = _read_csv(output.manifest_path)
    assert {"dataset", "noise_type", "annotation_type", "metric_scope"}.issubset(rows[0])
    assert any(
        row["dataset"] == "mvtec"
        and row["artifact_kind"] == "adapter_pipeline_summary"
        and row["source_command"].startswith("python scripts/run_adapter_pipeline.py")
        for row in rows
    )
    assert any(
        row["dataset"] == "wafer"
        and row["artifact_kind"] == "adapter_pipeline_summary"
        and "not a verified" in row["claim_boundary"]
        for row in rows
    )
    assert any(
        row["dataset"] == "mvtec"
        and row["noise_type"] == "morphology_replacement"
        and row["annotation_type"] == "manual_plausible"
        and row["metric_scope"] == "v0_reproducibility_check"
        and row["record_count"] == "1"
        for row in rows
    )
    assert any(
        row["dataset"] == "wafer"
        and row["noise_type"] == "location_replacement"
        and row["annotation_type"] == "literature_supported+manual_plausible"
        for row in rows
    )
    assert all(row["claim_boundary"] for row in rows)

    command_rows = _read_csv(output.command_manifest_path)
    assert [row["stage"] for row in command_rows] == [
        "adapter_pipeline_mvtec",
        "adapter_pipeline_wm811k",
        "noise_experiment",
    ]
    assert command_rows[0]["output_paths"] == str(mvtec_output.summary_path)


def test_build_paper_tables_protects_existing_outputs(tmp_path: Path) -> None:
    """Existing paper manifests should not be replaced without overwrite."""
    output_dir = tmp_path / "paper_tables"
    build_paper_tables(
        output_dir=output_dir,
        adapter_summary_paths=[],
        noise_summary_path=tmp_path / "missing_noise.json",
        suite_summary_path=tmp_path / "missing_suite.json",
    )

    with pytest.raises(FileExistsError, match="overwrite"):
        build_paper_tables(
            output_dir=output_dir,
            adapter_summary_paths=[],
            noise_summary_path=tmp_path / "missing_noise.json",
            suite_summary_path=tmp_path / "missing_suite.json",
        )


def test_build_paper_tables_cli_reports_outputs(tmp_path: Path) -> None:
    """The thin CLI should call the reusable builder and report generated paths."""
    noise_summary = _write_noise_summary(tmp_path / "noise" / "summary.json")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_paper_tables.py",
            "--output-dir",
            str(tmp_path / "paper_tables"),
            "--noise-summary",
            str(noise_summary),
            "--suite-summary",
            str(tmp_path / "missing_suite.json"),
            "--overwrite",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["manifest_path"] == str(tmp_path / "paper_tables" / PAPER_MANIFEST_FILENAME)
    assert payload["command_manifest_path"] == str(
        tmp_path / "paper_tables" / COMMAND_MANIFEST_FILENAME
    )
    assert payload["summary_path"] == str(tmp_path / "paper_tables" / SUMMARY_FILENAME)
    assert payload["manifest_row_count"] >= 1
    assert Path(payload["manifest_path"]).is_file()


def _write_noise_summary(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment_name": "v0_examples",
        "metric_scope": "v0_reproducibility_check",
        "metric_note": (
            "Metrics compare noisy pipeline outputs with clean-run references; "
            "they are not paper-grade ground-truth claims."
        ),
        "records": [
            _noise_record("mvtec_0001", "morphology_replacement"),
            _noise_record("wafer_0001", "location_replacement"),
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_suite_summary(
    path: Path,
    *,
    mvtec_summary: Path,
    wm811k_summary: Path,
    noise_summary: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "experiment_suite_v0",
        "commands": [
            _command("adapter_pipeline_mvtec", mvtec_summary),
            _command("adapter_pipeline_wm811k", wm811k_summary),
            _command("noise_experiment", noise_summary),
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _command(name: str, output_path: Path) -> dict[str, object]:
    return {
        "name": name,
        "command": ["python", "scripts/run_adapter_pipeline.py", "--output-dir", "runs/demo"],
        "passed": True,
        "output_paths": [str(output_path)],
    }


def _noise_record(case_id: str, noise_type: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "noise_level": 0.1,
        "noise_type": noise_type,
        "schema_validity_rate": 1.0,
        "entity_linking_accuracy": 1.0,
        "top_k_linking_accuracy": 1.0,
        "inconsistency_precision": 0.5,
        "inconsistency_recall": 0.5,
        "correction_accuracy": 0.5,
        "top_k_correction_accuracy": 0.5,
        "noise_recovery_rate": 0.5,
        "top_k_root_cause_accuracy": 0.5,
        "mrr": 0.5,
        "path_hit_rate": 0.5,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
