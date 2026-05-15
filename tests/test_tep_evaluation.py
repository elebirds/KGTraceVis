"""Tests for TEP RCA evaluation workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kgtracevis.workflows.tep_evaluation import (
    TepRcaEvaluationConfig,
    run_tep_rca_evaluation,
)


def test_tep_evaluation_uses_fault_number_only_as_reference(tmp_path: Path) -> None:
    """Existing TEP records should evaluate native RCA without leaking labels into scoring."""
    records_path = tmp_path / "tep_records.jsonl"
    records_path.write_text(
        json.dumps(
            {
                "dataset": "tep",
                "source": "tep_csv_rbc",
                "adapter": "tep",
                "case_id": "tep_fault_06_eval",
                "object": "Tennessee Eastman Process",
                "anomaly_type": "fault_06",
                "location": "process",
                "morphology": "multivariate_residual_shift",
                "variables": ["XMEAS_1", "XMV_3"],
                "variable_contributions": {"XMEAS_1": 0.7, "XMV_3": 0.3},
                "fault_number": 6,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output = run_tep_rca_evaluation(
        TepRcaEvaluationConfig(
            output_dir=tmp_path / "eval",
            input_records_path=records_path,
            top_k=3,
            overwrite=True,
        )
    )

    assert output.summary_path.is_file()
    assert output.table_path.is_file()
    assert output.summary["metrics"]["case_count"] == 1
    assert output.summary["cases"][0]["expected_root_cause_id"] == (
        "faultanchor:stream_1_a_feed_loss"
    )
    assert output.summary["cases"][0]["rank"] == 1
    assert output.summary["metrics"]["explicit_fault_label_ablation_top1_stability"] == 1.0
    assert output.summary["fault_coverage"] == {
        "record_source": "input_records",
        "record_count": 1,
        "requested_faults": None,
        "observed_faults": [6],
        "cases_per_fault": {"6": 1},
        "missing_requested_faults": None,
    }
    assert output.summary["explicit_fault_label_ablation"]["case_count"] == 1
    assert (
        output.summary["cases"][0]["explicit_fault_label_ablation_top1_candidate_id"]
        == output.summary["cases"][0]["top1_candidate_id"]
    )
    assert output.summary["cases"][0]["explicit_fault_label_ablation_top1_stable"] is True
    assert (
        "fault numbers are used only as evaluation references" in (output.summary["claim_boundary"])
    )


def test_tep_evaluation_defaults_align_with_tepkg_style(tmp_path: Path) -> None:
    """The dedicated TEP evaluation workflow uses Root-KGD as its only RCA path."""
    config = TepRcaEvaluationConfig(output_dir=tmp_path / "eval")

    assert config.window_size == 100
    assert config.row_stride == 25
    assert config.fault_free_max_rows is None
    assert config.n_components == 18


def test_tep_evaluation_cli_uses_native_root_kgd_provider(tmp_path: Path) -> None:
    """Evaluation CLI should use the single TEP Root-KGD provider."""
    records_path = _write_fault_06_record(tmp_path)
    output_dir = tmp_path / "eval_native"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_tep_rca.py",
            "--output-dir",
            str(output_dir),
            "--input-records",
            str(records_path),
            "--top-k",
            "3",
            "--overwrite",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    summary = json.loads(Path(payload["summary_path"]).read_text(encoding="utf-8"))
    adapter_summary = json.loads(Path(summary["adapter_summary_path"]).read_text(encoding="utf-8"))
    case = summary["cases"][0]
    root_cause = case["ranked_root_causes"][0]

    assert summary["config"]["tep_rca_reasoner"] == "tep_root_kgd"
    assert adapter_summary["pipeline"]["tep_rca_reasoner"] == "tep_root_kgd"
    assert case["expected_root_cause_id"] == "faultanchor:stream_1_a_feed_loss"
    assert case["rank"] == 1
    assert case["explicit_fault_label_ablation_top1_stable"] is True
    assert root_cause["candidate_id"] == "faultanchor:stream_1_a_feed_loss"
    assert root_cause["scoring_method"] == "tep_root_kgd"


def _write_fault_06_record(tmp_path: Path) -> Path:
    records_path = tmp_path / "tep_records.jsonl"
    records_path.write_text(
        json.dumps(
            {
                "dataset": "tep",
                "source": "tep_csv_rbc",
                "adapter": "tep",
                "case_id": "tep_fault_06_run_001_samples_000001_000100",
                "object": "Tennessee Eastman Process",
                "anomaly_type": "fault_06",
                "location": "process",
                "morphology": "multivariate_residual_shift",
                "variables": ["XMEAS_1", "XMV_3"],
                "variable_contributions": {"XMEAS_1": 0.7, "XMV_3": 0.3},
                "fault_number": 6,
                "simulation_run": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return records_path


def _write_tepkg_style_artifacts(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "TEP_KG"
    ranking_dir = artifact_dir / "outputs" / "rca"
    contributions_dir = artifact_dir / "data" / "processed" / "rca"
    ranking_dir.mkdir(parents=True)
    contributions_dir.mkdir(parents=True)
    (ranking_dir / "baseline_root_scores.csv").write_text(
        "\n".join(
            [
                "scenario_id,fault_number,simulation_run,rank,candidate_id,"
                "candidate_name,candidate_type,candidate_role,ranking_score,confidence",
                "tep_fault_06_run_001_samples_000001_000100,6,1,1,"
                "Fault06Stream1AFeedLoss,Fault 06 stream 1 A feed loss,FaultType,"
                "root_cause_anchor,0.97,0.93",
                "tep_fault_06_run_001_samples_000001_000100,6,1,2,"
                "Fault01Stream4ACRatio,Fault 01 stream 4 A/C ratio,FaultType,"
                "root_cause_anchor,0.44,0.51",
            ]
        ),
        encoding="utf-8",
    )
    (contributions_dir / "rbc_contributions.jsonl").write_text(
        json.dumps(
            {
                "scenario_id": "tep_fault_06_run_001_samples_000001_000100",
                "fault_number": 6,
                "simulation_run": 1,
                "top_variables": ["XMEAS_1", "XMV_3"],
                "graph_contributions": {
                    "variable:xmeas_1": 0.7,
                    "variable:xmv_3": 0.3,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_dir
