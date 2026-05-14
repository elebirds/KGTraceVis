"""Tests for TEP RCA evaluation workflow."""

from __future__ import annotations

import json
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
    assert output.summary["cases"][0]["expected_root_cause_id"] == "Fault06Stream1AFeedLoss"
    assert output.summary["cases"][0]["rank"] == 1
    assert "fault numbers are used only as evaluation references" in (
        output.summary["claim_boundary"]
    )
