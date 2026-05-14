"""Tests for adapter-to-pipeline orchestration."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from kgtracevis.experiments.adapter_pipeline import (
    EXPLANATION_SCOPE,
    SUMMARY_FILENAME,
    TABLE_COLUMNS,
    TABLE_FILENAME,
    run_adapter_pipeline,
)
from kgtracevis.kg_construction import build_candidate_kg, export_kg_csv


def test_run_adapter_pipeline_writes_evidence_and_candidate_summary(tmp_path: Path) -> None:
    """The helper should produce evidence files and candidate explanation summaries."""
    output = run_adapter_pipeline(
        "data/examples/records/mvtec_records.jsonl",
        tmp_path / "mvtec",
        dataset="mvtec",
        top_k=2,
    )

    assert output.summary_path == tmp_path / "mvtec" / SUMMARY_FILENAME
    assert output.table_path == tmp_path / "mvtec" / TABLE_FILENAME
    assert output.summary_path.is_file()
    assert output.table_path.is_file()
    assert len(output.evidence_paths) == 2
    assert all(path.is_file() for path in output.evidence_paths)

    summary = json.loads(output.summary_path.read_text(encoding="utf-8"))
    assert summary["artifact_type"] == "adapter_pipeline_v0"
    assert summary["explanation_scope"] == EXPLANATION_SCOPE
    assert "not verified process RCA claims" in summary["note"]
    assert summary["case_count"] == 2

    first_case = summary["cases"][0]
    assert first_case["adapter_name"] in {"mvtec", "ds_mvtec"}
    assert first_case["linked_entity_count"] > 0
    assert first_case["top_k_paths"]
    assert first_case["candidate_plausible_explanation_targets"]
    assert first_case["source_edge_provenance"]
    assert first_case["claim_boundary"].startswith("candidate/plausible explanation")
    assert first_case["generated_evidence"]["anomaly_type"] == "scratch"

    rows = _read_table(output.table_path)
    assert len(rows) == 2
    assert list(rows[0]) == list(TABLE_COLUMNS)
    assert rows[0]["case_id"] == "mvtec_fixture_clean_scratch"
    assert rows[0]["dataset"] == "mvtec"
    assert rows[0]["anomaly_type"] == "scratch"
    assert rows[0]["location"] == "surface"
    assert rows[0]["morphology"] == "linear"
    assert int(rows[0]["linked_entity_count"]) > 0
    assert int(rows[0]["path_count"]) > 0
    assert rows[0]["top_target_entity_id"]
    assert rows[0]["explanation_scope"] == EXPLANATION_SCOPE
    assert rows[0]["claim_boundary"].startswith("candidate/plausible explanation")


def test_run_adapter_pipeline_supports_wm811k_records(tmp_path: Path) -> None:
    """WM811K records should route through the wafer schema and produce paths."""
    output = run_adapter_pipeline(
        "data/examples/records/wm811k_records.jsonl",
        tmp_path / "wm811k",
        dataset="wafer",
        top_k=3,
    )

    cases = output.summary["cases"]
    assert [case["dataset"] for case in cases] == ["wafer", "wafer"]
    assert [case["adapter_name"] for case in cases] == ["wm811k", "wm811k"]
    assert all(case["top_k_paths"] for case in cases)
    assert all(case["candidate_plausible_explanation_targets"] for case in cases)

    rows = _read_table(output.table_path)
    assert len(rows) == 2
    assert [row["dataset"] for row in rows] == ["wafer", "wafer"]
    assert [row["adapter_name"] for row in rows] == ["wm811k", "wm811k"]
    assert rows[0]["case_id"] == "wm811k_fixture_clean_nearfull"
    assert rows[0]["anomaly_type"] == "nearfull"
    assert rows[0]["top_target_label"]
    assert float(rows[0]["best_score"]) > 0
    assert all(row["explanation_scope"] == EXPLANATION_SCOPE for row in rows)


def test_run_adapter_pipeline_uses_candidate_kg_overlay_for_wm811k_loc(
    tmp_path: Path,
) -> None:
    """KG overlays should prevent Loc evidence from routing through Nearfull."""
    nodes, edges, _summary = build_candidate_kg()
    nodes_path = tmp_path / "nodes_candidate.csv"
    edges_path = tmp_path / "edges_candidate.csv"
    export_kg_csv(nodes, edges, nodes_path=nodes_path, edges_path=edges_path)
    records_path = tmp_path / "wm811k_loc.jsonl"
    records_path.write_text(
        (
            '{"dataset":"wafer","adapter":"wm811k","case_id":"wm811k_loc_001",'
            '"wafer_id":"WLOC-001","predicted_pattern":"Loc",'
            '"failure_pattern":"Loc","classification_confidence":0.67,'
            '"wafer_map":[[0,0,0],[0,2,0],[0,0,0]],'
            '"annotation_type":"native_ground_truth"}\n'
        ),
        encoding="utf-8",
    )

    output = run_adapter_pipeline(
        records_path,
        tmp_path / "overlay",
        dataset="wafer",
        kg_node_paths=[nodes_path],
        kg_edge_paths=[edges_path],
    )

    case = output.summary["cases"][0]
    anomaly_link = next(
        link for link in case["linked_entities"] if link["field"] == "anomaly_type"
    )
    assert anomaly_link["selected_entity_id"] == "LocDefect"
    assert case["top_k_paths"]
    assert case["top_k_paths"][0]["target_entity_id"] != "GlueRemovalInsufficient"


def test_run_adapter_pipeline_default_kg_handles_wm811k_loc(tmp_path: Path) -> None:
    """Default web/script KG should not require an overlay for WM811K Loc."""
    records_path = tmp_path / "wm811k_loc.jsonl"
    records_path.write_text(
        (
            '{"dataset":"wafer","adapter":"wm811k","case_id":"wm811k_loc_default",'
            '"wafer_id":"WLOC-DEFAULT","predicted_pattern":"Loc",'
            '"failure_pattern":"Loc","classification_confidence":0.67,'
            '"wafer_map":[[0,0,0],[0,2,0],[0,0,0]],'
            '"annotation_type":"native_ground_truth"}\n'
        ),
        encoding="utf-8",
    )

    output = run_adapter_pipeline(records_path, tmp_path / "default", dataset="wafer")

    case = output.summary["cases"][0]
    selected = {
        link["field"]: link["selected_entity_id"]
        for link in case["linked_entities"]
        if link.get("selected_entity_id")
    }
    assert selected["anomaly_type"] == "LocDefect"
    assert selected["location"] == "WaferLocalLocation"
    assert selected["morphology"] == "WaferClusteredMorphology"
    assert case["top_k_paths"]
    assert case["top_k_paths"][0]["target_entity_id"] != "GlueRemovalInsufficient"


def test_run_adapter_pipeline_uses_native_tep_rca_provider_by_default(
    tmp_path: Path,
) -> None:
    """TEP records should enter Root-KGD RCA without a separate artifact mode."""
    records_path = _write_tep_record(tmp_path)
    nodes_path, edges_path = _write_empty_overlay_csv(tmp_path)

    output = run_adapter_pipeline(
        records_path,
        tmp_path / "tep_native",
        dataset="tep",
        kg_node_paths=[nodes_path],
        kg_edge_paths=[edges_path],
    )

    case = output.summary["cases"][0]
    assert output.summary["pipeline"]["root_cause_provider"] == "native"
    assert case["ranked_root_causes"]
    assert case["ranked_root_causes"][0]["candidate_id"] == "faultanchor:stream_1_a_feed_loss"
    assert case["ranked_root_causes"][0]["scoring_method"] == "tep_root_kgd"


def test_run_adapter_pipeline_protects_existing_summary(tmp_path: Path) -> None:
    """Existing summaries should not be replaced unless overwrite is explicit."""
    output_dir = tmp_path / "existing"
    run_adapter_pipeline(
        "data/examples/records/mvtec_records.jsonl",
        output_dir,
        dataset="mvtec",
    )

    with pytest.raises(FileExistsError, match="overwrite"):
        run_adapter_pipeline(
            "data/examples/records/mvtec_records.jsonl",
            output_dir,
            dataset="mvtec",
        )

    run_adapter_pipeline(
        "data/examples/records/mvtec_records.jsonl",
        output_dir,
        dataset="mvtec",
        overwrite=True,
    )


def test_run_adapter_pipeline_cli_reports_compact_result(tmp_path: Path) -> None:
    """The CLI should write artifacts and print a compact machine-readable result."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_adapter_pipeline.py",
            "--input",
            "data/examples/records/mvtec_records.jsonl",
            "--dataset",
            "mvtec",
            "--output-dir",
            str(tmp_path / "cli"),
            "--top-k",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["summary_path"] == str(tmp_path / "cli" / SUMMARY_FILENAME)
    assert payload["table_path"] == str(tmp_path / "cli" / TABLE_FILENAME)
    assert payload["evidence_count"] == 2
    assert payload["case_count"] == 2
    assert payload["explanation_scope"] == EXPLANATION_SCOPE
    assert Path(payload["summary_path"]).is_file()
    assert Path(payload["table_path"]).is_file()


def _read_table(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_tep_record(tmp_path: Path) -> Path:
    records_path = tmp_path / "tep_records.jsonl"
    records_path.write_text(
        (
            '{"dataset":"tep","case_id":"tep_native_adapter","object":"process",'
            '"anomaly_type":"process_fault","location":"reactor",'
            '"variables":["XMEAS_1","XMV_3"],'
            '"variable_contributions":{"XMEAS_1":0.7,"XMV_3":0.3},'
            '"fault_number":6,"confidence":0.75}\n'
        ),
        encoding="utf-8",
    )
    return records_path


def _write_empty_overlay_csv(tmp_path: Path) -> tuple[Path, Path]:
    nodes_path = tmp_path / "empty_nodes.csv"
    edges_path = tmp_path / "empty_edges.csv"
    nodes_path.write_text("id,name,label,scenario,aliases,description\n", encoding="utf-8")
    edges_path.write_text(
        (
            "head,relation,tail,scenario,source,evidence,confidence,weight,"
            "review_status,feedback_count,accepted_count,rejected_count\n"
        ),
        encoding="utf-8",
    )
    return nodes_path, edges_path
