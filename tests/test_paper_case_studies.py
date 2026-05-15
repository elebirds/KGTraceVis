"""Tests for paper-facing MVTec/WM811K case-study summaries."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from kgtracevis.workflows.paper_case_studies import (
    MVTEC_OBJECT_TABLE_FILENAME,
    SUMMARY_FILENAME,
    WM811K_PATTERN_TABLE_FILENAME,
    WM811K_STRATIFIED_PATTERN_TABLE_FILENAME,
    PaperCaseStudyEvaluationConfig,
    WM811KStratifiedBuildConfig,
    build_wm811k_stratified_records,
    run_paper_case_study_evaluation,
    summarize_mvtec_object_selection,
    summarize_wm811k_traceability,
)


def test_summarize_mvtec_object_selection_prefers_visual_and_explainable_object() -> None:
    """MVTec selection should combine visual behavior, KG coverage, and paths."""
    rows = summarize_mvtec_object_selection(
        records=[
            _mvtec_record("mvtec_bottle_test_good_000", "bottle", "good", "normal"),
            _mvtec_record("mvtec_bottle_test_crack_000", "bottle", "crack", "anomalous"),
            _mvtec_record("mvtec_cable_test_good_000", "cable", "good", "normal"),
            _mvtec_record("mvtec_cable_test_cut_000", "cable", "cut", "anomalous"),
            _mvtec_record("mvtec_cable_test_missing_000", "cable", "missing", "anomalous"),
        ],
        adapter_summary={
            "cases": [
                _case("mvtec_bottle_test_good_000", linked=3, path_count=0),
                _case("mvtec_bottle_test_crack_000", linked=3, path_count=0),
                _case("mvtec_cable_test_good_000", linked=4, path_count=1),
                _case("mvtec_cable_test_cut_000", linked=4, path_count=1),
                _case("mvtec_cable_test_missing_000", linked=4, path_count=1),
            ]
        },
        pipeline_summary={
            "sanity": {
                "records": [
                    {"case_id": "mvtec_bottle_test_crack_000", "mask_iou": 0.2},
                    {"case_id": "mvtec_cable_test_cut_000", "mask_iou": 0.6},
                    {"case_id": "mvtec_cable_test_missing_000", "mask_iou": 0.8},
                ]
            }
        },
    )

    selected = [row for row in rows if row["recommendation"].startswith("selected")]

    assert selected[0]["object"] == "cable"
    assert selected[0]["defect_anomalous_rate"] == 1.0
    assert selected[0]["explainable_path_rate"] == 1.0
    assert selected[0]["unique_top_targets"] == "MechanicalContact"


def test_summarize_wm811k_traceability_reports_pattern_coverage() -> None:
    """WM811K rows should expose observed/missing pattern coverage and bounded metrics."""
    rows = summarize_wm811k_traceability(
        records=[
            _wm811k_record("wm811k_1", "Loc", "Loc", 0.8),
            _wm811k_record("wm811k_2", "Near-full", "Near-full", 0.7),
        ],
        adapter_summary={
            "cases": [
                _case("wm811k_1", linked=4, path_count=1, source="wafer_thesis"),
                _case("wm811k_2", linked=4, path_count=1, source="wafer_thesis"),
            ]
        },
    )

    by_pattern = {row["pattern"]: row for row in rows}

    assert by_pattern["Loc"]["coverage_status"] == "observed"
    assert by_pattern["Loc"]["exact_accuracy"] == 1.0
    assert by_pattern["Near-full"]["mean_classifier_confidence"] == 0.7
    assert by_pattern["Donut"]["coverage_status"] == "not_observed_in_input"


def test_summarize_wm811k_traceability_bounds_pattern_accuracy_scope() -> None:
    """Pattern accuracy should use only native-vs-predicted comparable rows."""
    rows = summarize_wm811k_traceability(
        records=[
            _wm811k_record("wm811k_center_miss", "Center", "Loc", 0.0),
            {
                "case_id": "wm811k_native_only",
                "dataset": "wafer",
                "adapter": "wm811k",
                "failure_pattern": "Near-full",
                "annotation_type": "native_ground_truth",
                "classification_confidence": 0.4,
            },
            {
                "case_id": "wm811k_predicted_only",
                "dataset": "wafer",
                "adapter": "wm811k",
                "predicted_pattern": "Scratch",
                "classification_confidence": 0.3,
            },
        ],
        adapter_summary={"cases": []},
    )

    by_pattern = {row["pattern"]: row for row in rows}

    assert by_pattern["Center"]["coverage_status"] == "observed"
    assert by_pattern["Center"]["record_count"] == 1
    assert by_pattern["Center"]["predicted_count"] == 0
    assert by_pattern["Center"]["exact_comparable_count"] == 1
    assert by_pattern["Center"]["exact_correct_count"] == 0
    assert by_pattern["Center"]["exact_accuracy"] == 0.0
    assert by_pattern["Loc"]["record_count"] == 0
    assert by_pattern["Loc"]["predicted_count"] == 1
    assert by_pattern["Near-full"]["exact_comparable_count"] == 0
    assert by_pattern["Near-full"]["exact_accuracy"] == ""
    assert by_pattern["Center"]["mean_classifier_confidence"] == 0.0


def test_build_wm811k_stratified_records_uses_native_labels_without_accuracy_claim(
    tmp_path: Path,
) -> None:
    """The stratified WM811K build should cover patterns without claiming inference."""
    input_table = tmp_path / "wm811k.pkl"
    output_jsonl = tmp_path / "wm811k_stratified_records.jsonl"
    pd.DataFrame(
        [
            {
                "wafer_id": f"wafer-{index}",
                "waferMap": [[0, 1], [2, 2]],
                "failureType": [pattern],
            }
            for index, pattern in enumerate(
                [
                    "Center",
                    "Donut",
                    "Edge-Loc",
                    "Edge-Ring",
                    "Loc",
                    "Random",
                    "Scratch",
                    "Near-full",
                ]
            )
        ]
    ).to_pickle(input_table)

    output = build_wm811k_stratified_records(
        WM811KStratifiedBuildConfig(
            input_path=input_table,
            output_jsonl=output_jsonl,
            records_per_pattern=1,
            seed=7,
        )
    )

    records = [json.loads(line) for line in output.output_path.read_text().splitlines()]

    assert output.summary["record_count"] == 8
    assert output.summary["coverage_rate"] == 1.0
    assert output.summary["missing_patterns"] == []
    assert {record["native_failure_pattern"] for record in records} == set(
        output.summary["supported_patterns"]
    )
    assert all("predicted_pattern" not in record for record in records)
    assert all(record["classification_confidence"] is None for record in records)
    assert {record["record_source_scope"] for record in records} == {
        "native_label_stratified_sampling_not_classifier_performance"
    }
    assert {record["classifier"]["produces_root_cause"] for record in records} == {False}
    assert Path(output.summary_path).is_file()


def test_run_paper_case_study_evaluation_writes_json_and_tables(tmp_path: Path) -> None:
    """The workflow should write summary JSON and both paper-facing CSV tables."""
    mvtec_records = tmp_path / "mvtec_records.jsonl"
    wm811k_records = tmp_path / "wm811k_records.jsonl"
    mvtec_adapter = tmp_path / "mvtec_adapter.json"
    wm811k_adapter = tmp_path / "wm811k_adapter.json"
    mvtec_pipeline = tmp_path / "mvtec_pipeline.json"
    _write_jsonl(
        mvtec_records,
        [
            _mvtec_record("mvtec_bottle_test_good_000", "bottle", "good", "normal"),
            _mvtec_record("mvtec_bottle_test_crack_000", "bottle", "crack", "anomalous"),
        ],
    )
    _write_jsonl(
        wm811k_records,
        [_wm811k_record("wm811k_1", "Loc", "Loc", 0.8)],
    )
    _write_json(mvtec_adapter, {"case_count": 2, "cases": [_case("mvtec_bottle_test_crack_000")]})
    _write_json(wm811k_adapter, {"case_count": 1, "cases": [_case("wm811k_1")]})
    _write_json(
        mvtec_pipeline,
        {"sanity": {"records": [{"case_id": "mvtec_bottle_test_crack_000", "mask_iou": 0.5}]}},
    )

    output = run_paper_case_study_evaluation(
        PaperCaseStudyEvaluationConfig(
            output_dir=tmp_path / "paper_eval",
            mvtec_records_path=mvtec_records,
            mvtec_adapter_summary_path=mvtec_adapter,
            mvtec_pipeline_summary_path=mvtec_pipeline,
            wm811k_records_path=wm811k_records,
            wm811k_adapter_summary_path=wm811k_adapter,
        )
    )

    assert output.summary_path == tmp_path / "paper_eval" / SUMMARY_FILENAME
    assert output.mvtec_object_table_path == tmp_path / "paper_eval" / MVTEC_OBJECT_TABLE_FILENAME
    assert output.wm811k_pattern_table_path == (
        tmp_path / "paper_eval" / WM811K_PATTERN_TABLE_FILENAME
    )
    assert output.summary["mvtec"]["selected_object"] == "bottle"
    assert output.summary["wm811k"]["observed_patterns"] == ["Loc"]
    assert _read_csv(output.mvtec_object_table_path)[0]["claim_boundary"]

    with pytest.raises(FileExistsError, match="overwrite"):
        run_paper_case_study_evaluation(
            PaperCaseStudyEvaluationConfig(
                output_dir=tmp_path / "paper_eval",
                mvtec_records_path=mvtec_records,
                mvtec_adapter_summary_path=mvtec_adapter,
                wm811k_records_path=wm811k_records,
                wm811k_adapter_summary_path=wm811k_adapter,
            )
        )


def test_run_paper_case_study_evaluation_includes_wm811k_stratified_layer(
    tmp_path: Path,
) -> None:
    """The paper evaluator should write a separate stratified WM811K layer."""
    mvtec_records = tmp_path / "mvtec_records.jsonl"
    wm811k_records = tmp_path / "wm811k_records.jsonl"
    wm811k_stratified_records = tmp_path / "wm811k_stratified_records.jsonl"
    mvtec_adapter = tmp_path / "mvtec_adapter.json"
    wm811k_adapter = tmp_path / "wm811k_adapter.json"
    wm811k_stratified_adapter = tmp_path / "wm811k_stratified_adapter.json"
    stratified_record_rows = [
        _wm811k_native_label_record("wm811k_center", "Center"),
        _wm811k_native_label_record("wm811k_donut", "Donut"),
    ]
    _write_jsonl(
        mvtec_records,
        [_mvtec_record("mvtec_cable_test_cut_000", "cable", "cut", "anomalous")],
    )
    _write_jsonl(wm811k_records, [_wm811k_record("wm811k_1", "Loc", "Loc", 0.8)])
    _write_jsonl(wm811k_stratified_records, stratified_record_rows)
    _write_json(mvtec_adapter, {"case_count": 1, "cases": [_case("mvtec_cable_test_cut_000")]})
    _write_json(wm811k_adapter, {"case_count": 1, "cases": [_case("wm811k_1")]})
    _write_json(
        wm811k_stratified_adapter,
        {"case_count": 2, "cases": [_case("wm811k_center"), _case("wm811k_donut")]},
    )

    output = run_paper_case_study_evaluation(
        PaperCaseStudyEvaluationConfig(
            output_dir=tmp_path / "paper_eval",
            mvtec_records_path=mvtec_records,
            mvtec_adapter_summary_path=mvtec_adapter,
            wm811k_records_path=wm811k_records,
            wm811k_adapter_summary_path=wm811k_adapter,
            wm811k_stratified_records_path=wm811k_stratified_records,
            wm811k_stratified_adapter_summary_path=wm811k_stratified_adapter,
        )
    )

    stratified_table = tmp_path / "paper_eval" / WM811K_STRATIFIED_PATTERN_TABLE_FILENAME
    stratified_rows = _read_csv(stratified_table)
    by_pattern = {row["pattern"]: row for row in stratified_rows}

    assert output.wm811k_stratified_pattern_table_path == stratified_table
    assert output.summary["wm811k_stratified"]["observed_patterns"] == ["Center", "Donut"]
    assert output.summary["wm811k_stratified"]["exact_pattern_accuracy"] == ""
    assert by_pattern["Center"]["record_source_scope"] == (
        "native_label_stratified_sampling_not_classifier_performance"
    )
    assert by_pattern["Center"]["accuracy_scope"] == (
        "not_applicable_native_label_stratified_sampling"
    )


def test_evaluate_paper_case_studies_cli_reports_outputs(tmp_path: Path) -> None:
    """The CLI should stay thin and report generated artifact paths."""
    mvtec_records = tmp_path / "mvtec_records.jsonl"
    wm811k_records = tmp_path / "wm811k_records.jsonl"
    mvtec_adapter = tmp_path / "mvtec_adapter.json"
    wm811k_adapter = tmp_path / "wm811k_adapter.json"
    _write_jsonl(
        mvtec_records,
        [_mvtec_record("mvtec_cable_test_cut_000", "cable", "cut", "anomalous")],
    )
    _write_jsonl(wm811k_records, [_wm811k_record("wm811k_1", "Loc", "Loc", 0.8)])
    _write_json(mvtec_adapter, {"case_count": 1, "cases": [_case("mvtec_cable_test_cut_000")]})
    _write_json(wm811k_adapter, {"case_count": 1, "cases": [_case("wm811k_1")]})

    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_paper_case_studies.py",
            "--output-dir",
            str(tmp_path / "paper_eval"),
            "--mvtec-records",
            str(mvtec_records),
            "--mvtec-adapter-summary",
            str(mvtec_adapter),
            "--wm811k-records",
            str(wm811k_records),
            "--wm811k-adapter-summary",
            str(wm811k_adapter),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["selected_mvtec_object"] == "cable"
    assert Path(payload["summary_path"]).is_file()
    assert Path(payload["mvtec_object_table"]).is_file()
    assert Path(payload["wm811k_pattern_table"]).is_file()


def _mvtec_record(case_id: str, object_name: str, label: str, pred_label: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "dataset": "mvtec",
        "object": object_name,
        "defect_type": label,
        "pred_label": pred_label,
        "mask_stats": {"area_ratio": 0.1 if label != "good" else 0.0},
    }


def _wm811k_record(
    case_id: str,
    native: str,
    predicted: str,
    confidence: float,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "dataset": "wafer",
        "adapter": "wm811k",
        "failure_pattern": predicted,
        "native_failure_pattern": native,
        "predicted_pattern": predicted,
        "classification_confidence": confidence,
    }


def _wm811k_native_label_record(case_id: str, native: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "dataset": "wafer",
        "adapter": "wm811k",
        "failure_pattern": native,
        "native_failure_pattern": native,
        "annotation_type": "native_ground_truth",
        "record_source_scope": "native_label_stratified_sampling_not_classifier_performance",
        "classifier": {
            "backend": "native-label-stratified",
            "task": "native_pattern_stratified_sampling",
            "produces_root_cause": False,
        },
    }


def _case(
    case_id: str,
    *,
    linked: int = 4,
    path_count: int = 1,
    source: str = "manual_curation",
) -> dict[str, object]:
    paths = [
        {
            "path_id": f"path_{case_id}_{index}",
            "source_edges": [{"edge_id": f"edge_{case_id}_{index}", "source": source}],
        }
        for index in range(path_count)
    ]
    return {
        "case_id": case_id,
        "linked_entity_count": linked,
        "consistency_score": 1.0,
        "top_k_paths": paths,
        "candidate_plausible_explanation_targets": (
            [{"target_entity_id": "MechanicalContact"}] if path_count else []
        ),
        "source_edge_provenance": [
            {"edge_id": f"edge_{case_id}_{index}", "source": source} for index in range(path_count)
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
