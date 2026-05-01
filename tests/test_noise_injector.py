"""Tests for deterministic noise injection."""

from __future__ import annotations

from kgtracevis.noise.noise_injector import inject_noise
from kgtracevis.schema.validators import load_evidence_json


def test_visual_field_noise_is_deterministic_and_non_mutating() -> None:
    """Visual scalar corruption should be repeatable and preserve clean input."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    before = evidence.model_dump(mode="json")

    first = inject_noise(evidence, "morphology_replacement", 0.2, seed=7)
    second = inject_noise(evidence, "morphology_replacement", 0.2, seed=7)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.morphology != evidence.morphology
    assert first.raw_evidence.extra["is_noisy"] is True
    assert first.raw_evidence.extra["noise_level"] == 0.2
    assert first.raw_evidence.extra["noise_type"] == "morphology_replacement"
    assert first.raw_evidence.extra["corrupted_fields"] == ["morphology"]
    assert first.raw_evidence.extra["clean_reference"] == before
    assert evidence.model_dump(mode="json") == before


def test_list_field_noise_updates_variables_and_contributions() -> None:
    """List corruption should remove variables and matching contribution keys."""
    evidence = load_evidence_json("data/examples/tep_example.json")

    noisy = inject_noise(evidence, "variable_deletion", 0.1, seed=42)

    assert noisy.raw_evidence.variables == []
    assert noisy.raw_evidence.variable_contributions == {}
    assert noisy.raw_evidence.extra["corrupted_fields"] == [
        "raw_evidence.variables",
        "raw_evidence.variable_contributions",
    ]
    assert evidence.raw_evidence.variables == ["XMEAS_1"]
    assert evidence.raw_evidence.variable_contributions == {"XMEAS_1": 0.42}


def test_log_event_deletion_records_metadata() -> None:
    """Log-event deletion should support wafer multimodal examples."""
    evidence = load_evidence_json("data/examples/wafer_example.json")

    noisy = inject_noise(evidence, "log_event_deletion", 0.3, seed=42)

    assert noisy.raw_evidence.log_events == []
    assert noisy.raw_evidence.extra["is_noisy"] is True
    assert noisy.raw_evidence.extra["corrupted_fields"] == ["raw_evidence.log_events"]
