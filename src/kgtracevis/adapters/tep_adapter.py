"""Tennessee Eastman Process record adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kgtracevis.adapters._common import (
    adapter_metadata,
    copied_extra,
    first_value,
    float_dict,
    float_or_none,
    make_observation,
    merged_record,
    next_observation_occurrence,
    optional_text,
    source_value,
    text_list,
    text_value,
)
from kgtracevis.schema.evidence_schema import Evidence, EvidenceObservation, RawEvidence

CASE_KEYS = ("case_id", "sample_id", "record_id", "run_id", "id")
OBJECT_KEYS = ("object", "process_object", "process")
ANOMALY_KEYS = ("anomaly_type", "fault_type", "fault", "label")
LOCATION_KEYS = ("location", "process_unit", "unit", "process_location")
MORPHOLOGY_KEYS = ("morphology", "trend", "trend_shape", "pattern")
SEVERITY_KEYS = ("severity", "fault_severity", "anomaly_score")
CONFIDENCE_KEYS = ("confidence", "score")
VARIABLE_KEYS = ("variables", "variable_names", "abnormal_variables", "tags", "sensors")
CONTRIBUTION_KEYS = (
    "variable_contributions",
    "contributions",
    "attribution",
    "variable_scores",
    "contribution_scores",
)
DESCRIPTION_KEYS = ("description", "caption")
TEP_METADATA_KEYS = (
    "fault_id",
    "run_id",
    "window",
    "window_start",
    "window_end",
    "simulation_id",
    "sample_index",
    "timestep",
    "fault_start",
    "fault_duration",
)

KNOWN_KEYS = {
    "source",
    "timestamp",
    "extra",
    *CASE_KEYS,
    *OBJECT_KEYS,
    *ANOMALY_KEYS,
    *LOCATION_KEYS,
    *MORPHOLOGY_KEYS,
    *SEVERITY_KEYS,
    *CONFIDENCE_KEYS,
    *VARIABLE_KEYS,
    *CONTRIBUTION_KEYS,
    *DESCRIPTION_KEYS,
    *TEP_METADATA_KEYS,
}


def evidence_from_tep_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified evidence from a TEP-style time-series record."""
    data = merged_record(record, overrides)
    case_id = text_value(first_value(data, CASE_KEYS), "tep_unknown")
    object_name = text_value(first_value(data, OBJECT_KEYS), "process")
    anomaly_type = text_value(first_value(data, ANOMALY_KEYS), "unknown")
    location = optional_text(first_value(data, LOCATION_KEYS))
    morphology = optional_text(first_value(data, MORPHOLOGY_KEYS))
    severity = float_or_none(first_value(data, SEVERITY_KEYS))
    confidence = float_or_none(first_value(data, CONFIDENCE_KEYS))
    variables = text_list(first_value(data, VARIABLE_KEYS))
    contributions = float_dict(first_value(data, CONTRIBUTION_KEYS), keys=variables)
    metadata_extra = {
        key: data[key] for key in TEP_METADATA_KEYS if key in data and data[key] is not None
    }
    time_window = _time_window(metadata_extra)

    return Evidence(
        case_id=case_id,
        dataset="tep",
        source=source_value(data.get("source"), "time_series"),
        object=object_name,
        anomaly_type=anomaly_type,
        location=location,
        morphology=morphology,
        severity=severity,
        confidence=confidence,
        timestamp=optional_text(data.get("timestamp")),
        raw_evidence=RawEvidence(
            variables=variables,
            variable_contributions=contributions,
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(data, known_keys=KNOWN_KEYS, required=metadata_extra),
        ),
        observations=_tep_observations(
            case_id,
            object_name,
            anomaly_type,
            location,
            morphology,
            variables,
            contributions,
            severity,
            confidence,
            time_window,
        ),
        adapter=adapter_metadata("tep"),
    )


def _tep_observations(
    case_id: str,
    object_name: str,
    anomaly_type: str,
    location: str | None,
    morphology: str | None,
    variables: list[str],
    contributions: dict[str, float],
    severity: float | None,
    confidence: float | None,
    time_window: dict[str, Any] | None,
) -> list[EvidenceObservation]:
    observations: list[EvidenceObservation] = [
        make_observation(
            case_id,
            "object",
            object_name,
            confidence=confidence,
            source_ref="adapter:tep",
            raw_ref="object",
        ),
        make_observation(
            case_id,
            "anomaly_type",
            anomaly_type,
            confidence=confidence,
            source_ref="adapter:tep",
            raw_ref="anomaly_type",
        ),
    ]
    if location:
        observations.append(
            make_observation(
                case_id,
                "location",
                location,
                confidence=confidence,
                source_ref="adapter:tep",
                raw_ref="location",
            )
        )
    if morphology:
        observations.append(
            make_observation(
                case_id,
                "morphology",
                morphology,
                confidence=confidence,
                source_ref="adapter:tep",
                raw_ref="morphology",
            )
        )
    occurrences: dict[tuple[str, str], int] = {}
    for index, variable in enumerate(variables, start=1):
        contribution = contributions.get(variable)
        observations.append(
            make_observation(
                case_id,
                "variable",
                variable,
                value=contribution,
                value_type="contribution" if contribution is not None else None,
                confidence=confidence,
                source_ref="adapter:tep",
                raw_ref=f"raw_evidence.variables[{index - 1}]",
                time_window=time_window,
                metadata={"rank": index},
                occurrence=next_observation_occurrence(occurrences, "variable", variable),
            )
        )
    if severity is not None:
        observations.append(
            make_observation(
                case_id,
                "severity",
                "severity",
                value=severity,
                value_type="float",
                confidence=confidence,
                source_ref="adapter:tep",
                raw_ref="severity",
                time_window=time_window,
            )
        )
    if confidence is not None:
        observations.append(
            make_observation(
                case_id,
                "confidence",
                "adapter_confidence",
                value=confidence,
                value_type="float",
                confidence=confidence,
                source_ref="adapter:tep",
                raw_ref="confidence",
                time_window=time_window,
            )
        )
    return observations


def _time_window(metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    window = {
        key: metadata[key]
        for key in ("window", "window_start", "window_end", "sample_index", "timestep")
        if key in metadata
    }
    return window or None


def from_tep_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for TEP record conversion."""
    return evidence_from_tep_record(record, **overrides)
