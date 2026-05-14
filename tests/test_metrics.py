"""Tests for standalone metric functions."""

from __future__ import annotations

from kgtracevis.metrics import (
    correction_accuracy,
    entity_linking_accuracy,
    inconsistency_detection_precision_recall,
    mean_reciprocal_rank,
    noise_recovery_rate,
    path_hit_rate,
    schema_validity_rate,
    top_k_correction_accuracy,
    top_k_linking_accuracy,
    top_k_root_cause_accuracy,
)
from kgtracevis.schema.validators import load_evidence_json


def test_schema_validity_rate_handles_valid_invalid_and_empty_records() -> None:
    """Schema validity should be a pure rate over supplied records."""
    valid = load_evidence_json("data/examples/ds_mvtec_example.json")

    assert schema_validity_rate([valid, {"case_id": "missing_required_fields"}]) == 0.5
    assert schema_validity_rate([]) == 0.0


def test_linking_accuracy_metrics_cover_top1_and_topk() -> None:
    """Linking metrics should score exact predictions and candidate lists."""
    assert entity_linking_accuracy(["A", "B"], ["A", "C"]) == 0.5
    assert top_k_linking_accuracy(
        ["A", "B"],
        [[{"entity_id": "X"}, {"entity_id": "A"}], [{"entity_id": "C"}]],
        k=2,
    ) == 0.5
    assert top_k_linking_accuracy([], [], k=2) == 0.0


def test_inconsistency_detection_precision_recall_counts_fields() -> None:
    """Detection metrics should count field-level true and false decisions."""
    metrics = inconsistency_detection_precision_recall(
        [["anomaly_type", "raw_evidence.variables"], ["location"]],
        [["anomaly_type", "variable"], ["morphology"]],
    )

    assert metrics["precision"] == 2 / 3
    assert metrics["recall"] == 2 / 3
    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1


def test_inconsistency_detection_counts_unequal_case_lists() -> None:
    """Missing and extra case-level predictions should affect field counts."""
    metrics = inconsistency_detection_precision_recall(
        [["anomaly_type"], ["location"]],
        [["anomaly_type"], ["morphology"], ["variable"]],
    )

    assert metrics["precision"] == 1 / 3
    assert metrics["recall"] == 1 / 2
    assert metrics["tp"] == 1
    assert metrics["fp"] == 2
    assert metrics["fn"] == 1


def test_correction_and_noise_recovery_metrics_cover_topk() -> None:
    """Correction metrics should support direct values and candidate dicts."""
    candidates = [
        [{"suggested_entity_id": "Wrong"}, {"suggested_entity_id": "LinearMorphology"}],
        [{"suggested_value": "surface"}],
    ]

    assert (
        correction_accuracy(["linear morphology", "surface"], ["linear morphology", "wrong"])
        == 0.5
    )
    assert top_k_correction_accuracy(["LinearMorphology", "surface"], candidates, k=2) == 1.0
    assert noise_recovery_rate(["A"], ["A"]) == 1.0


def test_ranking_metrics_cover_hits_mrr_and_paths() -> None:
    """Ranking metrics should support target IDs and path dictionaries."""
    ranked = [
        [{"target_entity_id": "Wrong"}, {"candidate_id": "CauseA"}],
        [{"root_cause_candidate_id": "CauseB"}],
    ]
    paths = [
        [{"path_id": "p2"}, {"path_id": "p1"}],
        [{"nodes": ["A", "B"], "relations": ["CAUSES"]}],
    ]

    assert top_k_root_cause_accuracy(["CauseA", "Missing"], ranked, k=2) == 0.5
    assert mean_reciprocal_rank(["CauseA", "CauseB"], ranked) == 0.75
    assert path_hit_rate(["p1", {"nodes": ["A", "B"], "relations": ["CAUSES"]}], paths, k=2) == 1.0
    assert top_k_root_cause_accuracy([], [], k=2) == 0.0
