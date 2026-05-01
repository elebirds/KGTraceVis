"""Tests for the path ranking experiment script helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast


def _load_script_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "run_path_ranking",
        Path("scripts/run_path_ranking.py"),
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load run_path_ranking.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(ModuleType, module)


def test_path_ranking_payload_records_provenance() -> None:
    """Optional JSON output should preserve command and config provenance."""
    script = _load_script_module()
    evidence_path = Path("data/examples/ds_mvtec_example.json")
    records = script.analyze_evidence_files([evidence_path], top_k=2)

    payload = script.build_output_payload(
        records,
        evidence_path=evidence_path,
        example_dir=Path("data/examples"),
        output_dir=Path("outputs/path_ranking_v0"),
        top_k=2,
        command_args=["--evidence", str(evidence_path), "--write-json", "--top-k", "2"],
    )

    assert payload["artifact_type"] == "path_ranking_v0"
    assert payload["artifact_scope"] == "generated_reproducibility_output"
    assert payload["provenance"]["input_mode"] == "single_evidence"
    assert payload["provenance"]["evidence_path"] == str(evidence_path)
    assert payload["provenance"]["top_k"] == 2
    assert payload["case_count"] == 1
    assert payload["cases"][0]["case_id"] == "mvtec_0001"
    assert len(payload["cases"][0]["top_k_paths"]) <= 2
    assert payload["cases"][0]["top_k_paths"][0]["path_id"]


def test_analyze_evidence_files_passes_top_k_to_pipeline(monkeypatch: Any) -> None:
    """The script should delegate the requested ranking limit to core pipeline logic."""
    script = _load_script_module()
    calls: list[int] = []

    class FakeResult:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {
                "linked_entities": [],
                "consistency_score": 1.0,
                "inconsistent_fields": [],
                "correction_candidates": [],
                "top_k_paths": [{"path_id": f"path_{index}"} for index in range(4)],
            }

    class FakePipeline:
        def analyze(self, _evidence: Any, *, top_k: int) -> FakeResult:
            calls.append(top_k)
            return FakeResult()

    monkeypatch.setattr(script, "KGTracePipeline", FakePipeline)

    records = script.analyze_evidence_files(
        [Path("data/examples/ds_mvtec_example.json")],
        top_k=4,
    )

    assert calls == [4]
    assert len(records[0]["top_k_paths"]) == 4
