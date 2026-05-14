"""Tests for the reusable noise experiment workflow."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace

from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.workflows.noise_experiment import (
    NoiseExperimentConfig,
    NoiseExperimentResult,
    run_noise_experiment,
)


class _FakePipeline:
    def analyze(self, evidence: Evidence) -> AnalysisResult:
        selected = evidence.morphology or "unknown"
        return AnalysisResult(
            case_id=evidence.case_id,
            linked_entities=[
                {
                    "field": "morphology",
                    "selected_entity_id": selected,
                    "candidates": [{"entity_id": selected}],
                }
            ],
            consistency_score=0.5,
            inconsistent_fields=["morphology"]
            if evidence.raw_evidence.extra.get("is_noisy")
            else [],
            correction_candidates=[
                {
                    "field": "morphology",
                    "suggested_entity_id": "linear",
                }
            ]
            if evidence.raw_evidence.extra.get("is_noisy")
            else [],
            top_k_paths=[
                {
                    "path_id": "path_demo",
                    "target_entity_id": "RootCauseDemo",
                    "nodes": ["Anomaly", "RootCauseDemo"],
                    "relations": ["MAY_INDICATE"],
                }
            ],
        )


def test_run_noise_experiment_returns_structured_result(tmp_path: Path) -> None:
    """The workflow should write the same summary envelope without printing."""
    input_dir = tmp_path / "examples"
    input_dir.mkdir()
    shutil.copyfile(
        "data/examples/ds_mvtec_example.json",
        input_dir / "ds_mvtec_example.json",
    )
    noise_config = tmp_path / "noise.yaml"
    experiment_config = tmp_path / "experiment.yaml"
    noise_config.write_text(
        "seed: 7\nnoise_levels:\n  - 0.1\nsupported_noise_types:\n  - morphology_replacement\n",
        encoding="utf-8",
    )
    experiment_config.write_text(
        "\n".join(
            [
                "experiment_name: workflow_noise_test",
                "seed: 7",
                f"input_dir: {input_dir}",
                f"output_dir: {tmp_path / 'runs'}",
                "top_k: 3",
            ]
        ),
        encoding="utf-8",
    )

    result = run_noise_experiment(
        NoiseExperimentConfig(
            noise_config=noise_config,
            experiment_config=experiment_config,
        ),
        pipeline=_FakePipeline(),
    )

    assert result.output_path == tmp_path / "runs" / "workflow_noise_test" / "summary.json"
    assert result.summary["experiment_name"] == "workflow_noise_test"
    assert result.summary["case_count"] == 1
    assert result.summary["overall"]["record_count"] == 1
    assert result.records == result.summary["records"]
    assert json.loads(result.output_path.read_text(encoding="utf-8")) == result.summary


def test_run_noise_experiment_cli_preserves_summary_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """The CLI should remain a thin shell that reports output location and metrics."""
    cli = _load_cli_module()

    output_path = tmp_path / "runs" / "cli_noise_test" / "summary.json"
    captured_config: list[NoiseExperimentConfig] = []

    def fake_run_noise_experiment(config: NoiseExperimentConfig) -> NoiseExperimentResult:
        captured_config.append(config)
        return NoiseExperimentResult(
            output_path=output_path,
            records=[],
            summary={
                "experiment_name": "cli_noise_test",
                "case_count": 4,
                "overall": {"record_count": 0},
            },
        )

    monkeypatch.setattr(cli, "run_noise_experiment", fake_run_noise_experiment)
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: SimpleNamespace(
            noise_config=str(tmp_path / "noise.yaml"),
            experiment_config=str(tmp_path / "experiment.yaml"),
        ),
    )
    cli.main()

    completed = capsys.readouterr()
    assert captured_config == [
        NoiseExperimentConfig(
            noise_config=tmp_path / "noise.yaml",
            experiment_config=tmp_path / "experiment.yaml",
        )
    ]
    assert (
        f"noise experiment name=cli_noise_test, cases=4, records=0, output={output_path}"
        in completed.out
    )
    assert '"record_count": 0' in completed.out


def _load_cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_noise_experiment_cli",
        "scripts/run_noise_experiment.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
