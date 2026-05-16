"""Consolidated v0 experiment automation helpers."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from kgtracevis.experiments.adapter_pipeline import (
    SUMMARY_FILENAME as ADAPTER_PIPELINE_SUMMARY_FILENAME,
)
from kgtracevis.experiments.adapter_pipeline import (
    TABLE_FILENAME as ADAPTER_PIPELINE_TABLE_FILENAME,
)

METRIC_SCOPE_NOTE = (
    "V0 reproducibility outputs over checked-in examples and clean-run references; "
    "not paper-grade ground-truth claims."
)


@dataclass(frozen=True)
class CommandSpec:
    """One command in the local v0 experiment suite."""

    name: str
    command: list[str]
    expected_output: Path | None = None
    expected_outputs: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ExperimentCommandResult:
    """Captured result for one experiment command."""

    name: str
    command: list[str]
    return_code: int
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    summary: dict[str, Any] = field(default_factory=dict)
    output_paths: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return whether the command exited successfully."""
        return self.return_code == 0

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable command result."""
        return {
            "name": self.name,
            "command": self.command,
            "return_code": self.return_code,
            "passed": self.passed,
            "duration_seconds": round(self.duration_seconds, 3),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "summary": self.summary,
            "output_paths": self.output_paths,
        }


@dataclass(frozen=True)
class ExperimentSuiteResult:
    """Consolidated v0 experiment suite result."""

    suite_name: str
    generated_at: str
    provenance: dict[str, object]
    commands: list[ExperimentCommandResult]
    output_dir: Path
    metric_scope_note: str = METRIC_SCOPE_NOTE

    @property
    def passed(self) -> bool:
        """Return whether every suite command exited successfully."""
        return all(command.passed for command in self.commands)

    def table_rows(self) -> list[dict[str, object]]:
        """Return compact table-friendly rows for later human review."""
        rows: list[dict[str, object]] = []
        for command in self.commands:
            summary = command.summary
            rows.append(
                {
                    "stage": command.name,
                    "status": "passed" if command.passed else "failed",
                    "return_code": command.return_code,
                    "duration_seconds": round(command.duration_seconds, 3),
                    "primary_count": _primary_count(summary),
                    "issue_count": _nested_value(summary, "issue_count"),
                    "warning_count": _nested_value(summary, "warning_count"),
                    "output_paths": ";".join(command.output_paths),
                    "metric_scope": "v0_reproducibility_output",
                }
            )
        return rows

    def model_dump(self) -> dict[str, object]:
        """Return the suite result as a JSON-serializable payload."""
        return {
            "artifact_type": "experiment_suite_v0",
            "artifact_scope": "generated_reproducibility_output",
            "suite_name": self.suite_name,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "metric_scope_note": self.metric_scope_note,
            "provenance": self.provenance,
            "commands": [command.model_dump() for command in self.commands],
            "table_summary": self.table_rows(),
        }


def run_experiment_suite(
    *,
    suite_name: str = "v0_experiment_suite",
    output_root: str | Path = "runs",
    experiment_config_path: str | Path = "configs/experiment_config.yaml",
    noise_config_path: str | Path = "configs/noise_config.yaml",
    continue_on_failure: bool = False,
) -> ExperimentSuiteResult:
    """Run the local v0 experiment suite and write consolidated artifacts."""
    experiment_config = _read_yaml(Path(experiment_config_path))
    output_dir = Path(output_root) / suite_name
    output_dir.mkdir(parents=True, exist_ok=True)

    command_specs = build_default_command_specs(
        experiment_config=experiment_config,
        experiment_config_path=Path(experiment_config_path),
        noise_config_path=Path(noise_config_path),
        suite_output_dir=output_dir,
    )
    command_results: list[ExperimentCommandResult] = []
    for spec in command_specs:
        command_result = _run_command(spec)
        command_results.append(command_result)
        if not command_result.passed and not continue_on_failure:
            break

    suite_result = ExperimentSuiteResult(
        suite_name=suite_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        provenance={
            "command_name": "scripts/run_experiment_suite.py",
            "config_paths": {
                "experiment_config": str(experiment_config_path),
                "noise_config": str(noise_config_path),
            },
            "input_dir": str(experiment_config.get("input_dir", "data/examples")),
            "output_dir": str(output_dir),
            "git_commit": _git_commit(),
            "git_dirty": _git_dirty(),
            "metric_scope_note": METRIC_SCOPE_NOTE,
        },
        commands=command_results,
        output_dir=output_dir,
    )
    write_suite_outputs(suite_result)
    return suite_result


def build_default_command_specs(
    *,
    experiment_config: dict[str, Any],
    experiment_config_path: Path,
    noise_config_path: Path,
    suite_output_dir: Path,
) -> list[CommandSpec]:
    """Build the v0 command list from project defaults and config paths."""
    input_dir = Path(str(experiment_config.get("input_dir", "data/examples")))
    top_k = int(experiment_config.get("top_k", 5))
    path_ranking_output_dir = suite_output_dir / "path_ranking_v0"
    mvtec_adapter_output_dir = suite_output_dir / "adapter_pipeline_mvtec"
    wm811k_adapter_output_dir = suite_output_dir / "adapter_pipeline_wm811k"

    return [
        CommandSpec(
            name="examples_validation",
            command=[
                sys.executable,
                "scripts/run_examples.py",
                "--example-dir",
                str(input_dir),
            ],
        ),
        CommandSpec(
            name="neo4j_dry_run",
            command=[sys.executable, "scripts/import_kg.py", "--dry-run"],
        ),
        CommandSpec(
            name="noise_experiment",
            command=[
                sys.executable,
                "scripts/run_noise_experiment.py",
                "--noise-config",
                str(noise_config_path),
                "--experiment-config",
                str(experiment_config_path),
            ],
            expected_output=Path(str(experiment_config.get("output_dir", "runs")))
            / str(experiment_config.get("experiment_name", "noise_v0"))
            / "summary.json",
        ),
        CommandSpec(
            name="path_ranking",
            command=[
                sys.executable,
                "scripts/run_path_ranking.py",
                "--example-dir",
                str(input_dir),
                "--top-k",
                str(top_k),
                "--write-json",
                "--output-dir",
                str(path_ranking_output_dir),
            ],
            expected_output=path_ranking_output_dir / "path_ranking_summary.json",
        ),
        CommandSpec(
            name="adapter_pipeline_mvtec",
            command=[
                sys.executable,
                "scripts/run_adapter_pipeline.py",
                "--input",
                "data/examples/records/mvtec_records.jsonl",
                "--dataset",
                "mvtec",
                "--output-dir",
                str(mvtec_adapter_output_dir),
                "--top-k",
                str(top_k),
                "--overwrite",
            ],
            expected_output=mvtec_adapter_output_dir / ADAPTER_PIPELINE_SUMMARY_FILENAME,
            expected_outputs=(
                mvtec_adapter_output_dir / ADAPTER_PIPELINE_TABLE_FILENAME,
            ),
        ),
        CommandSpec(
            name="adapter_pipeline_wm811k",
            command=[
                sys.executable,
                "scripts/run_adapter_pipeline.py",
                "--input",
                "data/examples/records/wm811k_records.jsonl",
                "--dataset",
                "wafer",
                "--output-dir",
                str(wm811k_adapter_output_dir),
                "--top-k",
                str(top_k),
                "--overwrite",
            ],
            expected_output=wm811k_adapter_output_dir / ADAPTER_PIPELINE_SUMMARY_FILENAME,
            expected_outputs=(
                wm811k_adapter_output_dir / ADAPTER_PIPELINE_TABLE_FILENAME,
            ),
        ),
    ]


def write_suite_outputs(result: ExperimentSuiteResult) -> tuple[Path, Path]:
    """Write JSON and CSV table summaries for a suite run."""
    summary_path = result.output_dir / "summary.json"
    table_path = result.output_dir / "table_summary.csv"

    summary_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")

    rows = result.table_rows()
    fieldnames = [
        "stage",
        "status",
        "return_code",
        "duration_seconds",
        "primary_count",
        "issue_count",
        "warning_count",
        "output_paths",
        "metric_scope",
    ]
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return summary_path, table_path


def _run_command(spec: CommandSpec) -> ExperimentCommandResult:
    started = time.perf_counter()
    completed = subprocess.run(
        spec.command,
        check=False,
        capture_output=True,
        text=True,
    )
    duration = time.perf_counter() - started
    output_paths: list[str] = []
    summary = _extract_json_object(completed.stdout)
    for output_path in _expected_output_paths(spec):
        if output_path.exists():
            output_paths.append(str(output_path))

    if spec.expected_output is not None and spec.expected_output.exists():
        file_summary = _read_json_file(spec.expected_output)
        if file_summary:
            summary = _compact_summary(file_summary)

    return ExperimentCommandResult(
        name=spec.name,
        command=_report_command(spec.command),
        return_code=completed.returncode,
        duration_seconds=duration,
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
        summary=_compact_summary(summary),
        output_paths=output_paths,
    )


def _expected_output_paths(spec: CommandSpec) -> list[Path]:
    paths: list[Path] = []
    if spec.expected_output is not None:
        paths.append(spec.expected_output)
    paths.extend(spec.expected_outputs)
    return paths


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary:
        return {}
    if "summary" in summary and isinstance(summary["summary"], dict):
        nested = dict(summary["summary"])
        if "artifact_type" in summary:
            nested["artifact_type"] = summary["artifact_type"]
        return nested
    keys = (
        "validated",
        "kg_backend",
        "nodes",
        "edges",
        "node_count",
        "edge_count",
        "dry_run",
        "case_count",
        "record_count",
        "overall",
        "passed",
        "issue_count",
        "warning_count",
    )
    compact = {key: summary[key] for key in keys if key in summary}
    if "overall" in compact and isinstance(compact["overall"], dict):
        compact["record_count"] = compact["overall"].get("record_count")
    return compact or summary


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in reversed(list(enumerate(text))):
        if character != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if text[index + end :].strip():
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _git_dirty() -> bool | None:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def _report_command(command: list[str]) -> list[str]:
    if command and Path(command[0]) == Path(sys.executable):
        return ["python", *command[1:]]
    return command


def _tail(text: str, *, max_lines: int = 12) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _primary_count(summary: dict[str, Any]) -> object:
    for key in ("validated", "record_count", "case_count", "edge_count", "edges", "node_count"):
        value = _nested_value(summary, key)
        if value != "":
            return value
    return ""


def _nested_value(summary: dict[str, Any], key: str) -> object:
    if key in summary:
        return summary[key]
    overall = summary.get("overall")
    if isinstance(overall, dict) and key in overall:
        return overall[key]
    return ""
