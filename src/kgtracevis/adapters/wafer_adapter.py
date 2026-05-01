"""Wafer record adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kgtracevis.adapters._common import (
    copied_extra,
    first_value,
    float_dict,
    float_or_none,
    merged_record,
    optional_text,
    source_value,
    text_list,
    text_value,
)
from kgtracevis.schema.evidence_schema import Evidence, RawEvidence

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
    variables = text_list(first_value(data, VARIABLE_KEYS))
    metadata_extra = {
        key: data[key]
        for key in (*PATH_KEYS, *WAFER_METADATA_KEYS)
        if key in data and data[key] is not None
    }

    return Evidence(
        case_id=text_value(first_value(data, CASE_KEYS), "wafer_unknown"),
        dataset="wafer",
        source=source_value(data.get("source"), "multimodal"),
        object=text_value(first_value(data, OBJECT_KEYS), "wafer"),
        anomaly_type=text_value(first_value(data, ANOMALY_KEYS), "unknown"),
        location=optional_text(first_value(data, LOCATION_KEYS)),
        morphology=optional_text(first_value(data, MORPHOLOGY_KEYS)),
        severity=float_or_none(first_value(data, SEVERITY_KEYS)),
        confidence=float_or_none(first_value(data, CONFIDENCE_KEYS)),
        timestamp=optional_text(data.get("timestamp")),
        raw_evidence=RawEvidence(
            variables=variables,
            variable_contributions=float_dict(first_value(data, CONTRIBUTION_KEYS), keys=variables),
            log_events=text_list(first_value(data, LOG_EVENT_KEYS)),
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(data, known_keys=KNOWN_KEYS, required=metadata_extra),
        ),
    )


def from_wafer_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for wafer record conversion."""
    return evidence_from_wafer_record(record, **overrides)
