"""Tests for structured KG QA reports."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.kg_construction.qa import run_kg_qa

NODE_HEADER = "id,name,label,scenario,aliases,description"
EDGE_HEADER = (
    "head,relation,tail,scenario,source,evidence,confidence,weight,"
    "review_status,feedback_count,accepted_count,rejected_count"
)


def test_kg_qa_reports_raw_csv_issues_and_warnings(tmp_path: Path) -> None:
    """QA should report raw row problems without loading or editing the KG."""
    nodes_path = tmp_path / "nodes.csv"
    edges_path = tmp_path / "edges.csv"
    nodes_path.write_text(
        "\n".join(
            [
                NODE_HEADER,
                "ScratchDefect,Scratch defect,AnomalyType,mvtec,scratch,",
                "LinearMorphology,Linear morphology,Morphology,mvtec,linear,",
                "IsolatedNode,Isolated node,Object,mvtec,,",
            ]
        ),
        encoding="utf-8",
    )
    edges_path.write_text(
        "\n".join(
            [
                EDGE_HEADER,
                "ScratchDefect,HAS_MORPHOLOGY,LinearMorphology,mvtec,,row,0.9,0.1,auto,0,0,0",
                "ScratchDefect,HAS_MORPHOLOGY,LinearMorphology,mvtec,src,row,0.9,0.1,auto,0,0,0",
                "ScratchDefect,OCCURS_ON,MissingNode,mvtec,src,row,0.8,0.2,bad,-1,0,0",
                "ScratchDefect,HAS_CAUSE,LinearMorphology,mvtec,src,row,0.6,0.4,reviewed,0,0,0",
                "ScratchDefect,HAS_BAD_WEIGHT,LinearMorphology,mvtec,src,row,0.6,0.9,auto,0,0,0",
            ]
        ),
        encoding="utf-8",
    )

    report = run_kg_qa([nodes_path], [edges_path])
    codes = {finding.code for finding in report.findings}

    assert not report.passed
    assert "missing_provenance" in codes
    assert "duplicate_edge_id" in codes
    assert "missing_edge_endpoint" in codes
    assert "invalid_review_status" in codes
    assert "negative_feedback_counter" in codes
    assert "reviewed_low_confidence" in codes
    assert "weight_contract_violation" in codes
    assert "isolated_node" in codes
    assert report.summary()["issue_count"] >= 6
    assert report.summary()["warning_count"] >= 2


def test_kg_qa_checked_in_default_rows_have_no_issues() -> None:
    """Checked-in development KG rows should pass issue-severity QA."""
    report = run_kg_qa(
        ["data/kg/nodes.csv"],
        ["data/kg/edges.csv", "data/kg/mvtec_rca_reference.csv"],
    )

    assert report.issue_count == 0
    assert report.summary()["node_count"] > 0
    assert report.summary()["edge_count"] > 0
