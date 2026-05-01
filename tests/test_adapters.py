"""Tests for dataset-to-evidence adapters."""

from __future__ import annotations

from copy import deepcopy

from kgtracevis.adapters import (
    evidence_from_mvtec_record,
    evidence_from_tep_record,
    evidence_from_wafer_record,
)
from kgtracevis.schema.evidence_schema import Evidence


def test_mvtec_adapter_returns_valid_evidence_and_preserves_extra() -> None:
    """MVTec records should become image evidence without mutating the caller input."""
    record = {
        "sample_id": "mvtec_case_1",
        "object_name": "bottle",
        "defect_type": "scratch",
        "location": "surface",
        "shape": "linear",
        "severity": "0.4",
        "confidence": "0.8",
        "image_path": "images/bottle/001.png",
        "mask_path": "masks/bottle/001.png",
        "heatmap_path": "heatmaps/bottle/001.npy",
        "bbox": [10, 20, 30, 40],
        "caption": "Visual defect evidence.",
        "operator_note": {"shift": "A"},
    }
    before = deepcopy(record)

    evidence = evidence_from_mvtec_record(record)

    assert isinstance(evidence, Evidence)
    assert evidence.case_id == "mvtec_case_1"
    assert evidence.dataset == "mvtec"
    assert evidence.source == "image"
    assert evidence.object == "bottle"
    assert evidence.anomaly_type == "scratch"
    assert evidence.location == "surface"
    assert evidence.morphology == "linear"
    assert evidence.severity == 0.4
    assert evidence.confidence == 0.8
    assert evidence.raw_evidence.heatmap_path == "heatmaps/bottle/001.npy"
    assert evidence.raw_evidence.description == "Visual defect evidence."
    assert evidence.raw_evidence.extra["image_path"] == "images/bottle/001.png"
    assert evidence.raw_evidence.extra["mask_path"] == "masks/bottle/001.png"
    assert evidence.raw_evidence.extra["heatmap_path"] == "heatmaps/bottle/001.npy"
    assert evidence.raw_evidence.extra["bbox"] == [10, 20, 30, 40]
    assert evidence.raw_evidence.extra["operator_note"] == {"shift": "A"}
    assert record == before


def test_tep_adapter_returns_valid_evidence_and_preserves_extra() -> None:
    """TEP records should retain variables, contributions, and run metadata."""
    record = {
        "case_id": "tep_case_1",
        "fault_type": "process_fault",
        "process_unit": "reactor",
        "variables": ["XMEAS_1", "XMV_4"],
        "contributions": [0.42, 0.18],
        "fault_id": 6,
        "run_id": "run_007",
        "window_start": 120,
        "window_end": 180,
        "severity": 0.6,
        "score": 0.75,
        "description": "Variable contribution spike.",
        "source_file": "tep/run_007.csv",
    }
    before = deepcopy(record)

    evidence = evidence_from_tep_record(record)

    assert evidence.case_id == "tep_case_1"
    assert evidence.dataset == "tep"
    assert evidence.source == "time_series"
    assert evidence.object == "process"
    assert evidence.anomaly_type == "process_fault"
    assert evidence.location == "reactor"
    assert evidence.severity == 0.6
    assert evidence.confidence == 0.75
    assert evidence.raw_evidence.variables == ["XMEAS_1", "XMV_4"]
    assert evidence.raw_evidence.variable_contributions == {"XMEAS_1": 0.42, "XMV_4": 0.18}
    assert evidence.raw_evidence.description == "Variable contribution spike."
    assert evidence.raw_evidence.extra["fault_id"] == 6
    assert evidence.raw_evidence.extra["run_id"] == "run_007"
    assert evidence.raw_evidence.extra["window_start"] == 120
    assert evidence.raw_evidence.extra["window_end"] == 180
    assert evidence.raw_evidence.extra["source_file"] == "tep/run_007.csv"
    assert record == before


def test_wafer_adapter_returns_valid_evidence_and_preserves_extra() -> None:
    """Wafer records should retain image, log, and process-specific metadata."""
    record = {
        "case_id": "wafer_case_1",
        "wafer_id": "W-42",
        "defect_class": "nearfull",
        "wafer_location": "wafer_surface",
        "defect_pattern": "dense_particles",
        "log_events": ["etch_alarm", "particle_count_high"],
        "severity": 0.7,
        "confidence": 0.72,
        "image_path": "wafer/W-42.png",
        "log_path": "logs/W-42.jsonl",
        "tool_id": "etch_01",
        "chamber": "C2",
        "recipe": "R-17",
        "process_metadata": {"step": "etch"},
        "description": "Image-log wafer evidence.",
    }
    before = deepcopy(record)

    evidence = evidence_from_wafer_record(record)

    assert evidence.case_id == "wafer_case_1"
    assert evidence.dataset == "wafer"
    assert evidence.source == "multimodal"
    assert evidence.object == "wafer"
    assert evidence.anomaly_type == "nearfull"
    assert evidence.location == "wafer_surface"
    assert evidence.morphology == "dense_particles"
    assert evidence.raw_evidence.log_events == ["etch_alarm", "particle_count_high"]
    assert evidence.raw_evidence.description == "Image-log wafer evidence."
    assert evidence.raw_evidence.extra["wafer_id"] == "W-42"
    assert evidence.raw_evidence.extra["image_path"] == "wafer/W-42.png"
    assert evidence.raw_evidence.extra["log_path"] == "logs/W-42.jsonl"
    assert evidence.raw_evidence.extra["tool_id"] == "etch_01"
    assert evidence.raw_evidence.extra["process_metadata"] == {"step": "etch"}
    assert record == before


def test_adapter_keyword_overrides_do_not_mutate_record() -> None:
    """Keyword arguments should override copied input data only."""
    record = {"case_id": "mvtec_case_2", "object": "bottle", "defect_type": "scratch"}
    before = deepcopy(record)

    evidence = evidence_from_mvtec_record(record, defect_type="crack", confidence=0.9)

    assert evidence.anomaly_type == "crack"
    assert evidence.confidence == 0.9
    assert record == before
