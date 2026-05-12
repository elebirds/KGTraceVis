"""Tests for the unified evidence schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import (
    legacy_compatibility_warnings,
    load_evidence_json,
    missing_canonical_observation_facets,
    validate_canonical_observations,
)


def test_example_evidence_files_validate() -> None:
    """All checked-in example evidence files should validate."""
    paths = sorted(Path("data/examples").glob("*.json"))
    assert paths
    for path in paths:
        evidence = load_evidence_json(path)
        assert evidence.case_id
        assert evidence.dataset in {"mvtec", "tep", "wafer"}
        validate_canonical_observations(evidence)
        assert missing_canonical_observation_facets(evidence) == []


def test_evidence_observation_contract_validates_and_keeps_legacy_fields() -> None:
    """Evidence should support observation items without dropping top-level fields."""
    evidence = Evidence.model_validate(
        {
            "case_id": "schema_obs_1",
            "dataset": "tep",
            "source": "time_series",
            "object": "process",
            "anomaly_type": "process_fault",
            "raw_evidence": {"variables": ["XMEAS_1"]},
            "observations": [
                {
                    "obs_id": "obs_schema_obs_1_variable_xmeas_1",
                    "facet": "variable",
                    "name": "XMEAS_1",
                    "value": 0.42,
                    "value_type": "contribution",
                    "unit": "score",
                    "direction": "high",
                    "confidence": 0.75,
                    "source_ref": "adapter:tep",
                    "raw_ref": "raw_evidence.variables[0]",
                    "time_window": {"start": 10, "end": 20},
                    "metadata": {"rank": 1},
                }
            ],
            "adapter": {"name": "tep", "produces_root_cause": False},
        }
    )

    assert evidence.object == "process"
    assert evidence.raw_evidence.variables == ["XMEAS_1"]
    assert evidence.observations[0].obs_id == "obs_schema_obs_1_variable_xmeas_1"
    assert evidence.observations[0].facet == "variable"
    assert evidence.observations[0].value == 0.42
    assert evidence.adapter is not None
    assert evidence.adapter.produces_root_cause is False


def test_legacy_evidence_without_observations_or_adapter_still_validates() -> None:
    """Observation metadata should extend the schema without breaking legacy JSON."""
    evidence = Evidence.model_validate(
        {
            "case_id": "legacy_1",
            "dataset": "mvtec",
            "source": "image",
            "object": "bottle",
            "anomaly_type": "scratch",
            "raw_evidence": {"description": "legacy payload"},
        }
    )

    assert evidence.observations == []
    assert evidence.adapter is None
    assert evidence.raw_evidence.description == "legacy payload"
    assert missing_canonical_observation_facets(evidence) == ["anomaly_type", "object"]
    assert legacy_compatibility_warnings(evidence) == [
        "deprecated legacy reasoning fields are compatibility-only; "
        "add canonical observations for: anomaly_type, object"
    ]


def test_evidence_confidence_is_unit_scale() -> None:
    """Evidence confidence should reject raw unbounded detector scores."""
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Evidence.model_validate(
            {
                "case_id": "schema_confidence_1",
                "dataset": "mvtec",
                "source": "image",
                "object": "bottle",
                "anomaly_type": "visual_anomaly",
                "confidence": 3556.79,
            }
        )


def test_canonical_observation_validation_can_reject_legacy_payloads(tmp_path: Path) -> None:
    """Strict validation is available without breaking default compatibility."""
    path = tmp_path / "legacy.json"
    path.write_text(
        """
        {
          "case_id": "legacy_file_1",
          "dataset": "mvtec",
          "source": "image",
          "object": "bottle",
          "anomaly_type": "scratch",
          "raw_evidence": {"description": "legacy payload"}
        }
        """,
        encoding="utf-8",
    )

    assert load_evidence_json(path).case_id == "legacy_file_1"
    with pytest.raises(ValueError, match="deprecated legacy reasoning fields"):
        load_evidence_json(path, require_canonical_observations=True)
