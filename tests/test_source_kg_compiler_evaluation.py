"""Tests for source KG compiler parity and generated-only sample analysis."""

from __future__ import annotations

import importlib.util
import json
from io import StringIO
from pathlib import Path
from types import ModuleType

from kgtracevis.workflows.source_kg_compiler_evaluation import (
    SourceKGCompilerEvaluationConfig,
    SourceKGCompilerEvaluationResult,
    run_source_kg_compiler_evaluation,
)


class EmptyGraphLLM:
    """Fake LLM that preserves compiler calls but emits no extra KG facts."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.input_tokens += len(user_prompt.split())
        self.output_tokens += 4
        if "knowledge cards" in system_prompt:
            return json.dumps({"cards": []})
        if "canonical entities" in system_prompt:
            return json.dumps({"entities": []})
        if "construct edges" in system_prompt:
            return json.dumps({"edges": []})
        if "reasoning profiles" in system_prompt:
            return json.dumps({"profiles": {}})
        raise AssertionError(system_prompt)

    def repair_json(self, broken_json: str, error: str) -> str:
        return broken_json


def test_source_kg_compiler_evaluation_reports_strict_generated_only(
    tmp_path: Path,
) -> None:
    """Evaluation should not load default KG layers for sample analysis."""
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "minimal.md").write_text(
        "SCENARIO: mvtec\nENTITY: GeneratedOnlyThing | label=Other\n",
        encoding="utf-8",
    )
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    (baseline_dir / "knowledge_cards.json").write_text(
        json.dumps([{"card_id": "card_0001"}]),
        encoding="utf-8",
    )
    (baseline_dir / "entities.json").write_text(
        json.dumps([{"entity_id": "GeneratedOnlyThing"}]),
        encoding="utf-8",
    )
    (baseline_dir / "edges.json").write_text(json.dumps([]), encoding="utf-8")
    (baseline_dir / "nodes.csv").write_text(
        "entity_id,canonical_name,entity_type,aliases,description,scenario,source_card_ids\n"
        "GeneratedOnlyThing,GeneratedOnlyThing,Other,[],demo,mvtec,[]\n",
        encoding="utf-8",
    )
    (baseline_dir / "edges.csv").write_text(
        "edge_id,source,relation,target,scenario,evidence,source_card_ids,confidence,weight,"
        "review_status,feedback_count,accepted_count,rejected_count\n",
        encoding="utf-8",
    )
    result = run_source_kg_compiler_evaluation(
        SourceKGCompilerEvaluationConfig(
            materials_dir=materials_dir,
            output_dir=tmp_path / "run",
            baseline_output_dir=baseline_dir,
            sample_paths=(Path("data/examples/ds_mvtec_example.json"),),
            llm_client=EmptyGraphLLM(),
        )
    )

    assert result.report_path.is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["artifact_type"] == "source_kg_compiler_parity_real_sample_report_v1"
    assert report["summary"]["qa_status"] == "passed"
    assert report["summary"]["validation_status"] == "passed"
    assert report["baseline_comparison"]["status"] == "compared"
    assert report["strict_runtime"]["strict_generated_only"] is True
    assert report["strict_runtime"]["default_kg_layers_loaded"] is False
    assert report["strict_runtime"]["tep_root_kgd_reasoner_enabled"] is True
    assert report["strict_runtime"]["loaded_node_files"] == [
        result.compiled_output_dir.joinpath("nodes.csv").as_posix()
    ]
    assert report["strict_runtime"]["loaded_edge_files"] == [
        result.compiled_output_dir.joinpath("edges.csv").as_posix()
    ]
    assert report["strict_runtime"]["node_count"] == 1
    assert report["strict_runtime"]["edge_count"] == 0
    assert "data/kg/nodes.csv" in report["strict_runtime"]["forbidden_default_layers"]

    sample = report["samples"][0]
    assert sample["path"].endswith("data/examples/ds_mvtec_example.json")
    assert sample["path_exists"] is False
    assert sample["selected_link_count"] == 0
    assert "no_path" in sample["reasonableness_flags"]
    assert "low_coverage" in sample["reasonableness_flags"]
    assert report["summary"]["sample_flag_counts"]["no_path"] == 1


def test_source_kg_compiler_evaluation_progress_logs_key_stages_and_limit(
    tmp_path: Path,
) -> None:
    """Default progress callback should expose long-running evaluation stages."""
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "a.md").write_text(
        "SCENARIO: mvtec\nENTITY: GeneratedOnlyThing | label=Other\n",
        encoding="utf-8",
    )
    (materials_dir / "b.md").write_text(
        "SCENARIO: wafer\nENTITY: WaferOnlyThing | label=Other\n",
        encoding="utf-8",
    )
    stream = StringIO()
    evaluate_cli = _load_evaluation_cli_module()

    result = run_source_kg_compiler_evaluation(
        SourceKGCompilerEvaluationConfig(
            materials_dir=materials_dir,
            output_dir=tmp_path / "run",
            baseline_output_dir=None,
            sample_paths=(Path("data/examples/ds_mvtec_example.json"),),
            llm_client=EmptyGraphLLM(),
            source_limit=1,
            llm_concurrency=3,
            progress_callback=evaluate_cli.make_progress_logger(stream),
        )
    )

    log = stream.getvalue()
    for stage in (
        "evaluation_config",
        "compile_start",
        "source_units",
        "knowledge_cards",
        "entities",
        "edges",
        "domain_profiles",
        "sample_analysis",
        "baseline_comparison",
        "report_written",
    ):
        assert f"stage={stage}" in log
    assert "llm_start stage=knowledge_cards" in log
    assert "llm_finish stage=knowledge_cards" in log
    assert "calls=" in log
    assert "tokens=" in log
    assert "source_limit=1" in log
    assert "llm_concurrency=3" in log
    assert "smoke_hint=" in log
    assert result.report["config"]["source_limit"] == 1
    assert result.report["config"]["llm_concurrency"] == 3
    assert result.report["summary"]["counts"]["source_units"] == 1


def test_source_kg_compiler_evaluation_without_progress_callback_is_quiet(
    tmp_path: Path,
    capsys,
) -> None:
    """Quiet mode is implemented by not passing a progress callback."""
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "minimal.md").write_text(
        "SCENARIO: mvtec\nENTITY: GeneratedOnlyThing | label=Other\n",
        encoding="utf-8",
    )

    run_source_kg_compiler_evaluation(
        SourceKGCompilerEvaluationConfig(
            materials_dir=materials_dir,
            output_dir=tmp_path / "run",
            baseline_output_dir=None,
            sample_paths=(Path("data/examples/ds_mvtec_example.json"),),
            llm_client=EmptyGraphLLM(),
        )
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_evaluation_cli_quiet_suppresses_progress(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """The CLI --quiet flag should not install the default progress logger."""
    output_dir = tmp_path / "run"
    seen: dict[str, object] = {}
    evaluate_cli = _load_evaluation_cli_module()

    def fake_run(
        config: SourceKGCompilerEvaluationConfig,
    ) -> SourceKGCompilerEvaluationResult:
        seen["progress_callback"] = config.progress_callback
        seen["llm_concurrency"] = config.llm_concurrency
        return SourceKGCompilerEvaluationResult(
            report={"summary": {"sample_count": 0}},
            report_path=output_dir / "source_kg_compiler_evaluation_report.json",
            compiled_output_dir=output_dir / "compiled_kg",
        )

    class FakeOpenAICompatibleSourceKGLLM:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(evaluate_cli, "run_source_kg_compiler_evaluation", fake_run)
    monkeypatch.setattr(
        evaluate_cli,
        "OpenAICompatibleSourceKGLLM",
        FakeOpenAICompatibleSourceKGLLM,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_source_kg_compiler.py",
            "--output-dir",
            output_dir.as_posix(),
            "--quiet",
        ],
    )

    evaluate_cli.main()

    captured = capsys.readouterr()
    assert seen["progress_callback"] is None
    assert seen["llm_concurrency"] == 4
    assert captured.err == ""
    assert "source_kg_compiler_evaluation_report.json" in captured.out


def _load_evaluation_cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "evaluate_source_kg_compiler_cli",
        "scripts/evaluate_source_kg_compiler.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
