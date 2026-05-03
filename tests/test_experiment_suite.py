"""Tests for consolidated experiment suite helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from kgtracevis.experiments.suite import (
    ExperimentCommandResult,
    ExperimentSuiteResult,
    _report_command,
    build_default_command_specs,
    write_suite_outputs,
)


def test_build_default_command_specs_include_v0_checks(tmp_path: Path) -> None:
    """The suite command list should include the expected local v0 stages."""
    specs = build_default_command_specs(
        experiment_config={"input_dir": "data/examples", "top_k": 3},
        experiment_config_path=Path("configs/experiment_config.yaml"),
        noise_config_path=Path("configs/noise_config.yaml"),
        suite_output_dir=tmp_path,
    )

    assert [spec.name for spec in specs] == [
        "examples_validation",
        "kg_build_validation",
        "kg_qa",
        "neo4j_dry_run",
        "noise_experiment",
        "path_ranking",
        "adapter_pipeline_mvtec",
        "adapter_pipeline_wm811k",
    ]
    path_command = specs[5].command
    assert "--top-k" in path_command
    assert path_command[path_command.index("--top-k") + 1] == "3"
    assert specs[2].expected_output == tmp_path / "kg_qa_report.json"
    assert specs[6].expected_output == (
        tmp_path / "adapter_pipeline_mvtec" / "adapter_pipeline_summary.json"
    )
    assert specs[6].expected_outputs == (
        tmp_path / "adapter_pipeline_mvtec" / "adapter_pipeline_table.csv",
    )
    assert specs[7].command[specs[7].command.index("--dataset") + 1] == "wafer"


def test_report_command_normalizes_local_python_path() -> None:
    """Persisted provenance should not include machine-local interpreter paths."""
    assert _report_command([sys.executable, "scripts/run_examples.py"]) == [
        "python",
        "scripts/run_examples.py",
    ]


def test_write_suite_outputs_creates_json_and_table(tmp_path: Path) -> None:
    """Suite output should include a JSON report and compact CSV table."""
    result = ExperimentSuiteResult(
        suite_name="suite_test",
        generated_at="2026-05-01T00:00:00+00:00",
        provenance={"command_name": "scripts/run_experiment_suite.py"},
        commands=[
            ExperimentCommandResult(
                name="examples_validation",
                command=["python", "scripts/run_examples.py"],
                return_code=0,
                duration_seconds=0.25,
                stdout_tail="",
                stderr_tail="",
                summary={"validated": 3},
                output_paths=["runs/example.json", "runs/example.csv"],
            )
        ],
        output_dir=tmp_path,
    )

    summary_path, table_path = write_suite_outputs(result)

    assert summary_path.exists()
    assert table_path.exists()
    assert "experiment_suite_v0" in summary_path.read_text(encoding="utf-8")
    table_text = table_path.read_text(encoding="utf-8")
    assert "examples_validation,passed,0" in table_text
    assert "runs/example.json;runs/example.csv" in table_text
