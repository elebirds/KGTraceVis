"""Tests for dataset-to-evidence adapters."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from kgtracevis.adapters import (
    evidence_from_mvtec_record,
    evidence_from_tep_record,
    evidence_from_wafer_record,
    evidence_from_wm811k_record,
)
from kgtracevis.adapters.batch import evidence_from_records, load_records
from kgtracevis.mask.mask_feature_extractor import summarize_mask_features
from kgtracevis.mask.wafer_map_features import normalize_wafer_map_features
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import missing_canonical_observation_facets


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
    assert evidence.adapter is not None
    assert evidence.adapter.produces_root_cause is False
    assert missing_canonical_observation_facets(evidence) == []
    assert _observation(evidence, "anomaly_type").name == "scratch"
    assert _observation(evidence, "morphology").obs_id == "obs_mvtec_case_1_morphology_linear"
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
    variable_observation = _observation(evidence, "variable")
    assert variable_observation.name == "XMEAS_1"
    assert variable_observation.value == 0.42
    assert variable_observation.value_type == "contribution"
    assert variable_observation.time_window == {"window_start": 120, "window_end": 180}
    assert evidence.adapter is not None
    assert evidence.adapter.produces_root_cause is False
    assert missing_canonical_observation_facets(evidence) == []
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
    log_observation = _observation(evidence, "log_event")
    assert log_observation.name == "etch_alarm"
    assert log_observation.metadata == {"rank": 1}
    assert _observation(evidence, "morphology").name == "dense_particles"
    assert evidence.adapter is not None
    assert evidence.adapter.produces_root_cause is False
    assert missing_canonical_observation_facets(evidence) == []
    assert record == before


def test_adapter_keyword_overrides_do_not_mutate_record() -> None:
    """Keyword arguments should override copied input data only."""
    record = {"case_id": "mvtec_case_2", "object": "bottle", "defect_type": "scratch"}
    before = deepcopy(record)

    evidence = evidence_from_mvtec_record(record, defect_type="crack", confidence=0.9)

    assert evidence.anomaly_type == "crack"
    assert evidence.confidence == 0.9
    assert record == before


def test_adapter_observation_ids_remain_unique_for_repeated_values() -> None:
    """Repeated observed variable/log values should still get stable unique IDs."""
    tep = evidence_from_tep_record(
        {"case_id": "dup_case", "variables": ["XMEAS_1", "XMEAS_1"]}
    )
    wafer = evidence_from_wafer_record(
        {"case_id": "dup_case", "log_events": ["etch_alarm", "etch_alarm"]}
    )

    tep_variable_ids = [
        observation.obs_id for observation in tep.observations if observation.facet == "variable"
    ]
    wafer_event_ids = [
        observation.obs_id
        for observation in wafer.observations
        if observation.facet == "log_event"
    ]

    assert tep_variable_ids == [
        "obs_dup_case_variable_xmeas_1",
        "obs_dup_case_variable_xmeas_1_02",
    ]
    assert wafer_event_ids == [
        "obs_dup_case_log_event_etch_alarm",
        "obs_dup_case_log_event_etch_alarm_02",
    ]


def test_mask_feature_helpers_derive_stable_geometry_terms() -> None:
    """Precomputed mask geometry should deterministically derive adapter evidence fields."""
    features = summarize_mask_features(
        {
            "centroid": [0.5, 0.45],
            "area_ratio": 0.16,
            "eccentricity": 0.91,
            "component_count": 1,
        }
    )

    assert features["location"] == "surface"
    assert features["morphology"] == "linear"
    assert features["severity"] == 0.16
    assert features["mask_stats"]["centroid_norm"] == (0.5, 0.45)


def test_wafer_map_feature_helpers_support_precomputed_stats_and_tiny_arrays() -> None:
    """Wafer descriptors should work without model downloads or heavy vision packages."""
    precomputed = normalize_wafer_map_features(
        {"defect_density": 0.72, "zone": "wafer_surface"},
        pattern="Near-full",
    )
    from_array = normalize_wafer_map_features(
        wafer_map=[[2, 2, 2], [2, 0, 2], [2, 2, 2]],
        pattern="nearfull",
    )

    assert precomputed["derived_location"] == "wafer_surface"
    assert precomputed["derived_morphology"] == "dense_particles"
    assert precomputed["derived_severity"] == 0.72
    assert from_array["failed_die_count"] == 8
    assert from_array["die_count"] == 9
    assert from_array["derived_location"] == "wafer_surface"
    assert from_array["derived_morphology"] == "dense_particles"


def test_mvtec_adapter_derives_fallback_fields_from_mask_stats() -> None:
    """MVTec fallback should use mask geometry while keeping KG analysis empty."""
    record = {
        "case_id": "mvtec_mask_fallback",
        "object": "bottle",
        "defect_type": "scratch",
        "mask_stats": {
            "centroid": [0.48, 0.52],
            "area_ratio": 0.16,
            "eccentricity": 0.93,
            "component_count": 1,
        },
        "detector": {"name": "fixture_detector", "pred_score": 0.81},
        "root_cause": "should_not_be_copied",
        "extra": {"root_cause": "nested_should_not_be_copied"},
    }

    evidence = evidence_from_mvtec_record(record)

    assert evidence.location == "surface"
    assert evidence.morphology == "linear"
    assert evidence.severity == 0.16
    assert evidence.confidence == 0.81
    assert evidence.raw_evidence.extra["mask_stats"]["eccentricity"] == 0.93
    assert evidence.raw_evidence.extra["detector"]["pred_score"] == 0.81
    assert _observation(evidence, "location").source_ref == "mask_geometry"
    assert _observation(evidence, "morphology").obs_id == (
        "obs_mvtec_mask_fallback_morphology_linear"
    )
    assert missing_canonical_observation_facets(evidence) == []
    assert evidence.kg_analysis.model_dump() == _empty_kg_analysis()
    assert evidence.adapter is not None
    assert evidence.adapter.produces_root_cause is False
    assert "root_cause" not in evidence.raw_evidence.extra
    assert _root_cause_keys(evidence) == []


def test_wm811k_adapter_returns_schema_valid_wafer_evidence() -> None:
    """WM811K records should remain dataset='wafer' and avoid root-cause outputs."""
    record = {
        "case_id": "wm811k_case_1",
        "wafer_id": "W-811K-1",
        "failure_pattern": "Near-full",
        "classification_confidence": 0.88,
        "defect_density": 0.72,
        "zone": "wafer_surface",
        "morphology": "dense_particles",
        "wafer_map_path": "fixtures/wm811k/W-811K-1.npy",
        "annotation_type": "native_ground_truth",
        "root_cause": "should_not_be_copied",
        "extra": {"candidate_root_cause": "nested_should_not_be_copied"},
    }

    evidence = evidence_from_wm811k_record(record)

    assert isinstance(evidence, Evidence)
    assert evidence.dataset == "wafer"
    assert evidence.source == "image"
    assert evidence.object == "wafer"
    assert evidence.anomaly_type == "nearfull"
    assert evidence.location == "wafer_surface"
    assert evidence.morphology == "dense_particles"
    assert evidence.severity == 0.72
    assert evidence.confidence == 0.88
    assert evidence.adapter is not None
    assert evidence.adapter.name == "wm811k"
    assert evidence.adapter.metadata["schema_dataset"] == "wafer"
    assert evidence.adapter.produces_root_cause is False
    assert evidence.raw_evidence.extra["wm811k"]["original_pattern"] == "Near-full"
    assert evidence.raw_evidence.extra["descriptor_stats"]["derived_location"] == "wafer_surface"
    assert _observation(evidence, "spatial_pattern").obs_id == (
        "obs_wm811k_case_1_spatial_pattern_nearfull"
    )
    assert _observation(evidence, "anomaly_type").source_ref == "dataset_label"
    assert missing_canonical_observation_facets(evidence) == []
    assert evidence.kg_analysis.model_dump() == _empty_kg_analysis()
    assert "root_cause" not in evidence.raw_evidence.extra
    assert "candidate_root_cause" not in evidence.raw_evidence.extra
    assert _root_cause_keys(evidence) == []


def test_record_fixtures_convert_to_schema_valid_adapter_evidence() -> None:
    """Checked-in tiny fixtures should exercise MVTec and WM811K adapter contracts."""
    mvtec_records = load_records(Path("data/examples/records/mvtec_records.jsonl"))
    wm811k_records = load_records(Path("data/examples/records/wm811k_records.jsonl"))

    evidence_items = [
        *evidence_from_records(mvtec_records),
        *evidence_from_records(wm811k_records),
    ]

    assert [item.adapter.name if item.adapter else None for item in evidence_items] == [
        "mvtec",
        "mvtec",
        "wm811k",
        "wm811k",
    ]
    assert [item.dataset for item in evidence_items] == ["mvtec", "mvtec", "wafer", "wafer"]
    for evidence in evidence_items:
        assert isinstance(evidence, Evidence)
        assert missing_canonical_observation_facets(evidence) == []
        assert evidence.kg_analysis.model_dump() == _empty_kg_analysis()
        assert evidence.adapter is not None
        assert evidence.adapter.produces_root_cause is False
        assert _root_cause_keys(evidence) == []


def _observation(evidence: Evidence, facet: str):
    return next(observation for observation in evidence.observations if observation.facet == facet)


def _empty_kg_analysis() -> dict[str, object]:
    return {
        "linked_entities": [],
        "consistency_score": None,
        "inconsistent_fields": [],
        "correction_candidates": [],
        "top_k_paths": [],
    }


def _root_cause_keys(evidence: Evidence) -> list[str]:
    root_keys = {
        "root_cause",
        "root_causes",
        "candidate_root_cause",
        "candidate_root_causes",
        "ranked_causes",
    }
    keys: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in root_keys:
                    keys.append(key)
                collect(nested)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(evidence.model_dump(mode="json"))
    return keys
