"""Wafer record adapter."""

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

CASE_KEYS = ("case_id", "sample_id", "record_id", "wafer_id", "id")
OBJECT_KEYS = ("object", "wafer_object", "wafer")
ANOMALY_KEYS = ("anomaly_type", "defect_type", "defect", "defect_class", "failure_pattern", "label")
LOCATION_KEYS = ("location", "wafer_location", "die_location", "zone")
MORPHOLOGY_KEYS = ("morphology", "pattern", "defect_pattern", "shape")
SEVERITY_KEYS = ("severity", "defect_severity", "anomaly_score")
CONFIDENCE_KEYS = ("confidence", "score")
LOG_EVENT_KEYS = ("log_events", "events", "alarms", "alarm_events")
VARIABLE_KEYS = ("variables", "process_variables", "sensors")
CONTRIBUTION_KEYS = ("variable_contributions", "contributions", "variable_scores")
DESCRIPTION_KEYS = ("description", "caption")
PATH_KEYS = ("image_path", "map_path", "wafer_map_path", "log_path", "process_log_path")
WAFER_METADATA_KEYS = (
    "wafer_id",
    "lot_id",
    "batch_id",
    "die_id",
    "tool_id",
    "chamber",
    "recipe",
    "process_step",
    "process_metadata",
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
    *LOG_EVENT_KEYS,
    *VARIABLE_KEYS,
    *CONTRIBUTION_KEYS,
    *DESCRIPTION_KEYS,
    *PATH_KEYS,
    *WAFER_METADATA_KEYS,
}


def evidence_from_wafer_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified evidence from a wafer image/log/process record."""
    data = merged_record(record, overrides)
    case_id = text_value(first_value(data, CASE_KEYS), "wafer_unknown")
    object_name = text_value(first_value(data, OBJECT_KEYS), "wafer")
    anomaly_type = text_value(first_value(data, ANOMALY_KEYS), "unknown")
    location = optional_text(first_value(data, LOCATION_KEYS))
    morphology = optional_text(first_value(data, MORPHOLOGY_KEYS))
    severity = float_or_none(first_value(data, SEVERITY_KEYS))
    confidence = float_or_none(first_value(data, CONFIDENCE_KEYS))
    variables = text_list(first_value(data, VARIABLE_KEYS))
    contributions = float_dict(first_value(data, CONTRIBUTION_KEYS), keys=variables)
    log_events = text_list(first_value(data, LOG_EVENT_KEYS))
    metadata_extra = {
        key: data[key]
        for key in (*PATH_KEYS, *WAFER_METADATA_KEYS)
        if key in data and data[key] is not None
    }

    return Evidence(
        case_id=case_id,
        dataset="wafer",
        source=source_value(data.get("source"), "multimodal"),
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
            log_events=log_events,
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(data, known_keys=KNOWN_KEYS, required=metadata_extra),
        ),
        observations=_wafer_observations(
            case_id,
            object_name,
            anomaly_type,
            location,
            morphology,
            variables,
            contributions,
            log_events,
            severity,
            confidence,
        ),
        adapter=adapter_metadata("wafer"),
    )


def _wafer_observations(
    case_id: str,
    object_name: str,
    anomaly_type: str,
    location: str | None,
    morphology: str | None,
    variables: list[str],
    contributions: dict[str, float],
    log_events: list[str],
    severity: float | None,
    confidence: float | None,
) -> list[EvidenceObservation]:
    observations: list[EvidenceObservation] = [
        make_observation(
            case_id,
            "object",
            object_name,
            confidence=confidence,
            source_ref="adapter:wafer",
            raw_ref="object",
        ),
        make_observation(
            case_id,
            "anomaly_type",
            anomaly_type,
            confidence=confidence,
            source_ref="adapter:wafer",
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
                source_ref="adapter:wafer",
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
                source_ref="adapter:wafer",
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
                source_ref="adapter:wafer",
                raw_ref=f"raw_evidence.variables[{index - 1}]",
                metadata={"rank": index},
                occurrence=next_observation_occurrence(occurrences, "variable", variable),
            )
        )
    for index, event in enumerate(log_events, start=1):
        observations.append(
            make_observation(
                case_id,
                "log_event",
                event,
                confidence=confidence,
                source_ref="adapter:wafer",
                raw_ref=f"raw_evidence.log_events[{index - 1}]",
                metadata={"rank": index},
                occurrence=next_observation_occurrence(occurrences, "log_event", event),
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
                source_ref="adapter:wafer",
                raw_ref="severity",
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
                source_ref="adapter:wafer",
                raw_ref="confidence",
            )
        )
    return observations


def from_wafer_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for wafer record conversion."""
    return evidence_from_wafer_record(record, **overrides)
