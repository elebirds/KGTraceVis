"""Tests for batch evidence loading, conversion, and writing."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from kgtracevis.adapters.batch import (
    evidence_from_records,
    load_records,
    summarize_evidence,
    write_evidence_files,
    write_evidence_jsonl,
)
from kgtracevis.schema.validators import load_evidence_json


def test_load_records_supports_json_list_object_jsonl_and_csv(tmp_path: Path) -> None:
    """Batch loaders should accept the supported curated record formats."""
    records = [
        {"dataset": "mvtec", "case_id": "mvtec_1", "object": "bottle", "anomaly_type": "scratch"},
        {"dataset": "tep", "case_id": "tep_1", "fault_type": "process_fault"},
    ]

    json_list = tmp_path / "records.json"
    json_list.write_text(json.dumps(records), encoding="utf-8")
    assert load_records(json_list) == records

    json_object = tmp_path / "records_object.json"
    json_object.write_text(json.dumps({"records": records}), encoding="utf-8")
    assert load_records(json_object) == records

    jsonl_path = tmp_path / "records.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    assert load_records(jsonl_path) == records

    csv_path = tmp_path / "records.csv"
    csv_path.write_text(
        "dataset,case_id,object,anomaly_type\nmvtec,mvtec_2,bottle,scratch\n",
        encoding="utf-8",
    )
    assert load_records(csv_path) == [
        {"dataset": "mvtec", "case_id": "mvtec_2", "object": "bottle", "anomaly_type": "scratch"}
    ]


def test_evidence_from_records_dispatches_per_record_dataset_and_preserves_input() -> None:
    """Per-record datasets should select the existing single-record adapters."""
    records = [
        {
            "dataset": "mvtec",
            "case_id": "mvtec_1",
            "object": "bottle",
            "anomaly_type": "scratch",
            "image_path": "images/001.png",
        },
        {
            "dataset": "tep",
            "case_id": "tep_1",
            "fault_type": "process_fault",
            "variables": ["XMEAS_1"],
            "contributions": [0.4],
        },
        {
            "dataset": "wafer",
            "case_id": "wafer_1",
            "defect_class": "nearfull",
            "log_events": ["alarm_high_particle"],
        },
    ]
    before = deepcopy(records)

    evidence_items = evidence_from_records(records)

    assert [item.dataset for item in evidence_items] == ["mvtec", "tep", "wafer"]
    assert evidence_items[0].raw_evidence.extra["image_path"] == "images/001.png"
    assert evidence_items[1].raw_evidence.variables == ["XMEAS_1"]
    assert evidence_items[2].raw_evidence.log_events == ["alarm_high_particle"]
    assert records == before


def test_evidence_from_records_supports_explicit_dataset() -> None:
    """An explicit dataset should be used when records omit dataset."""
    evidence_items = evidence_from_records(
        [
            {
                "case_id": "mvtec_explicit",
                "object": "cable",
                "anomaly_type": "cut",
                "mask_path": "masks/001.png",
            }
        ],
        dataset="mvtec",
    )

    assert evidence_items[0].dataset == "mvtec"
    assert evidence_items[0].raw_evidence.extra["mask_path"] == "masks/001.png"


def test_evidence_from_records_requires_dataset_when_not_explicit() -> None:
    """Missing dataset should fail clearly instead of selecting an adapter silently."""
    with pytest.raises(ValueError, match="missing dataset"):
        evidence_from_records([{"case_id": "unknown_1"}])


def test_write_evidence_outputs_json_files_jsonl_and_summary(tmp_path: Path) -> None:
    """Generated evidence should round-trip through both output modes."""
    evidence_items = evidence_from_records(
        [
            {"dataset": "mvtec", "case_id": "case/one", "object": "bottle", "defect": "scratch"},
            {"dataset": "tep", "case_id": "case_two", "fault": "process_fault"},
        ]
    )

    output_dir = tmp_path / "evidence"
    written_files = write_evidence_files(evidence_items, output_dir)
    assert [path.name for path in written_files] == ["case_one.json", "case_two.json"]
    assert load_evidence_json(written_files[0]).case_id == "case/one"

    jsonl_path = write_evidence_jsonl(evidence_items, tmp_path / "evidence.jsonl")
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["case_id"] for line in lines] == ["case/one", "case_two"]

    summary = summarize_evidence(evidence_items)
    assert summary.model_dump() == {
        "total_count": 2,
        "by_dataset": {"mvtec": 1, "tep": 1},
        "by_source": {"image": 1, "time_series": 1},
    }


def test_write_evidence_files_protects_existing_outputs(tmp_path: Path) -> None:
    """Existing per-case files should not be replaced unless overwrite is explicit."""
    evidence_items = evidence_from_records(
        [{"dataset": "wafer", "case_id": "wafer_1", "defect": "nearfull"}]
    )
    write_evidence_files(evidence_items, tmp_path)

    with pytest.raises(FileExistsError, match="overwrite"):
        write_evidence_files(evidence_items, tmp_path)

    write_evidence_files(evidence_items, tmp_path, overwrite=True)


def test_write_evidence_files_rejects_duplicate_output_names(tmp_path: Path) -> None:
    """Case IDs that sanitize to the same filename should not overwrite each other."""
    evidence_items = evidence_from_records(
        [
            {"dataset": "mvtec", "case_id": "case/one", "object": "bottle"},
            {"dataset": "mvtec", "case_id": "case one", "object": "bottle"},
        ]
    )

    with pytest.raises(ValueError, match="same file"):
        write_evidence_files(evidence_items, tmp_path, overwrite=True)


def test_generate_evidence_cli_reports_compact_summary(tmp_path: Path) -> None:
    """The CLI should summarize destinations without printing every JSON filename."""
    input_path = tmp_path / "records.jsonl"
    input_path.write_text(
        "\n".join(
            json.dumps(record)
            for record in [
                {"dataset": "mvtec", "case_id": "cli_one", "object": "bottle"},
                {"dataset": "tep", "case_id": "cli_two", "fault_type": "process_fault"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_evidence.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "evidence"),
            "--output-jsonl",
            str(tmp_path / "evidence.jsonl"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["total_count"] == 2
    assert summary["by_dataset"] == {"mvtec": 1, "tep": 1}
    assert summary["outputs"]["output_dir_count"] == 2
    assert summary["outputs"]["output_jsonl_count"] == 2
    assert "cli_one.json" not in result.stdout


def test_generate_evidence_cli_preflights_jsonl_overwrite(tmp_path: Path) -> None:
    """JSONL overwrite failures should happen before per-case files are written."""
    input_path = tmp_path / "records.json"
    output_dir = tmp_path / "evidence"
    output_jsonl = tmp_path / "evidence.jsonl"
    input_path.write_text(
        json.dumps([{"dataset": "mvtec", "case_id": "cli_existing", "object": "bottle"}]),
        encoding="utf-8",
    )
    output_jsonl.write_text("existing\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_evidence.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--output-jsonl",
            str(output_jsonl),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "pass --overwrite" in result.stderr
    assert not output_dir.exists()
