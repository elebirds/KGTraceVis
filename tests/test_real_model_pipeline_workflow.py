"""Tests for real-model pipeline workflow orchestration."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from kgtracevis.workflows import real_model_pipeline as workflow
from kgtracevis.workflows.real_model_pipeline import (
    RealModelPipelineConfig,
    RealModelPipelineResult,
)

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "run_real_model_pipeline.py"


def _load_run_script() -> Any:
    spec = importlib.util.spec_from_file_location("run_real_model_pipeline", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_model_pipeline_workflow_returns_summary_without_printing(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """Workflow orchestration should return structured output and leave printing to CLI."""

    class FakeMVTecBackend:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeWM811KBackend:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    def fake_download_openvino_checkpoint(
        repo_id: str,
        filename: str,
        destination_dir: Path,
    ) -> Path:
        checkpoint = destination_dir / "model.xml"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text("<xml />", encoding="utf-8")
        return checkpoint

    def fake_download_hf_file(
        repo_id: str,
        filename: str,
        destination_dir: Path,
        *,
        repo_type: str | None = None,
    ) -> Path:
        del repo_id, filename, repo_type
        image = destination_dir / "source.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"image")
        return image

    def fake_write_jsonl_records(
        records: list[dict[str, Any]],
        output_path: Path,
        *,
        overwrite: bool,
    ) -> Path:
        assert overwrite is True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(record) for record in records),
            encoding="utf-8",
        )
        return output_path

    def fake_run_adapter_pipeline(
        input_path: Path,
        output_dir: Path,
        *,
        dataset: str,
        top_k: int,
        overwrite: bool,
    ) -> SimpleNamespace:
        assert input_path.exists()
        assert top_k == 3
        assert overwrite is True
        return SimpleNamespace(
            summary_path=output_dir / "adapter_pipeline_summary.json",
            table_path=output_dir / "adapter_pipeline_table.csv",
            summary={"case_count": 1 if dataset == "mvtec" else 2},
        )

    monkeypatch.setattr(workflow, "AnomalibMVTecBackend", FakeMVTecBackend)
    monkeypatch.setattr(workflow, "TorchWM811KBackend", FakeWM811KBackend)
    monkeypatch.setattr(
        workflow,
        "_download_openvino_checkpoint",
        fake_download_openvino_checkpoint,
    )
    monkeypatch.setattr(workflow, "_download_hf_file", fake_download_hf_file)
    monkeypatch.setattr(workflow, "_resize_image", lambda image_path, size: None)
    monkeypatch.setattr(
        workflow,
        "download_wm811k_resnet",
        lambda **kwargs: {
            "checkpoint": tmp_path / "wm811k.pt",
            "repo_id": kwargs["repo_id"],
            "filename": kwargs["filename"],
            "backend": "torch-resnet34",
        },
    )
    monkeypatch.setattr(
        workflow,
        "download_wm811k_input_table",
        lambda **kwargs: {
            "input_table": tmp_path / "wm811k.pkl",
            "source_repo": kwargs["repo_id"],
            "filename": kwargs["filename"],
            "repo_type": kwargs["repo_type"],
        },
    )
    monkeypatch.setattr(
        workflow,
        "build_mvtec_records",
        lambda *args, **kwargs: [{"case_id": "m"}],
    )
    monkeypatch.setattr(
        workflow,
        "build_wm811k_records",
        lambda *args, **kwargs: [{"case_id": "w"}],
    )
    monkeypatch.setattr(workflow, "write_jsonl_records", fake_write_jsonl_records)
    monkeypatch.setattr(workflow, "run_adapter_pipeline", fake_run_adapter_pipeline)

    result = workflow.run_real_model_pipeline(
        RealModelPipelineConfig(output_root=tmp_path / "run", overwrite=True)
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert result.output_path == tmp_path / "run" / "summary.json"
    assert result.summary["artifact_type"] == "real_model_pipeline_v0"
    assert result.summary["output_root"] == str(tmp_path / "run")
    assert result.summary["mvtec"]["case_count"] == 1
    assert result.summary["wm811k"]["case_count"] == 2
    assert json.loads(result.output_path.read_text(encoding="utf-8")) == result.summary


def test_real_model_pipeline_script_is_argparse_shell(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI should delegate to the workflow and print the returned summary."""
    run_script = _load_run_script()
    captured_config: dict[str, RealModelPipelineConfig] = {}

    def fake_run(config: RealModelPipelineConfig) -> RealModelPipelineResult:
        captured_config["config"] = config
        return RealModelPipelineResult(
            output_path=config.output_root / "summary.json",
            output_root=config.output_root,
            summary={
                "artifact_type": "real_model_pipeline_v0",
                "output_root": str(config.output_root),
                "mvtec": {"case_count": 1},
                "wm811k": {"case_count": 1},
            },
        )

    monkeypatch.setattr(
        run_script,
        "parse_args",
        lambda: argparse.Namespace(
            output_root=tmp_path / "run",
            mvtec_repo="mvtec/repo",
            mvtec_checkpoint="model.tar",
            mvtec_image_repo="image/repo",
            mvtec_image="image.png",
            wm811k_repo="wm/repo",
            wm811k_checkpoint="model.pt",
            wm811k_input_repo="input/repo",
            wm811k_input_file="table.pkl",
            wm811k_input_repo_type="dataset",
            overwrite=True,
        ),
    )
    monkeypatch.setattr(run_script, "run_real_model_pipeline", fake_run)

    run_script.main()

    config = captured_config["config"]
    assert config.output_root == tmp_path / "run"
    assert config.mvtec_repo == "mvtec/repo"
    assert config.wm811k_input_repo_type == "dataset"
    assert config.overwrite is True
    printed_summary = json.loads(capsys.readouterr().out)
    assert printed_summary["artifact_type"] == "real_model_pipeline_v0"
    assert printed_summary["output_root"] == str(tmp_path / "run")
