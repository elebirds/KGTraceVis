"""WM811K wafer-map record adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kgtracevis.adapters._common import (
    adapter_metadata,
    copied_extra,
    first_value,
    float_or_none,
    make_observation,
    merged_record,
    optional_text,
    source_value,
    text_value,
)
from kgtracevis.mask.wafer_map_features import normalize_wafer_map_features
from kgtracevis.schema.evidence_schema import Evidence, EvidenceObservation, RawEvidence

CASE_KEYS = ("case_id", "sample_id", "record_id", "wafer_id", "id")
PATTERN_KEYS = ("failure_pattern", "pattern", "label", "predicted_pattern", "defect_class")
CONFIDENCE_KEYS = ("confidence", "classification_confidence", "score", "prediction_score")
LOCATION_KEYS = ("location", "zone", "wafer_location")
MORPHOLOGY_KEYS = ("morphology", "defect_pattern", "shape")
SEVERITY_KEYS = ("severity", "defect_density", "anomaly_score")
DESCRIPTION_KEYS = ("description", "caption")
PATH_KEYS = ("wafer_map_path", "map_path", "image_path", "saliency_path", "attention_map_path")
DESCRIPTOR_KEYS = (
    "descriptor_stats",
    "wafer_map",
    "map_shape",
    "die_count",
    "failed_die_count",
    "defect_density",
)
METADATA_KEYS = (
    "dataset",
    "adapter",
    "adapter_name",
    "source_dataset",
    "annotation_type",
    "wafer_id",
    "lot_id",
    "batch_id",
)
ROOT_CAUSE_KEYS = (
    "root_cause",
    "root_causes",
    "candidate_root_cause",
    "candidate_root_causes",
    "ranked_causes",
    "ranked_root_causes",
    "top_k_paths",
)

KNOWN_KEYS = {
    "source",
    "timestamp",
    "extra",
    *CASE_KEYS,
    *PATTERN_KEYS,
    *CONFIDENCE_KEYS,
    *LOCATION_KEYS,
    *MORPHOLOGY_KEYS,
    *SEVERITY_KEYS,
    *DESCRIPTION_KEYS,
    *PATH_KEYS,
    *DESCRIPTOR_KEYS,
    *METADATA_KEYS,
    *ROOT_CAUSE_KEYS,
}


def evidence_from_wm811k_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified wafer evidence from a model-independent WM811K record."""
    data = merged_record(record, overrides)
    case_id = text_value(first_value(data, CASE_KEYS), "wm811k_unknown")
    raw_pattern = text_value(first_value(data, PATTERN_KEYS), "unknown")
    anomaly_type = _canonical_pattern(raw_pattern)
    confidence = float_or_none(first_value(data, CONFIDENCE_KEYS))
    descriptor_stats = normalize_wafer_map_features(
        data.get("descriptor_stats") if isinstance(data.get("descriptor_stats"), Mapping) else None,
        wafer_map=data.get("wafer_map") if isinstance(data.get("wafer_map"), list) else None,
        pattern=anomaly_type,
        die_count=data.get("die_count"),
        failed_die_count=data.get("failed_die_count"),
        defect_density=data.get("defect_density"),
        map_shape=data.get("map_shape"),
        zone=first_value(data, LOCATION_KEYS),
        morphology=first_value(data, MORPHOLOGY_KEYS),
    )
    location = optional_text(first_value(data, LOCATION_KEYS)) or optional_text(
        descriptor_stats.get("derived_location")
    )
    morphology = optional_text(first_value(data, MORPHOLOGY_KEYS)) or optional_text(
        descriptor_stats.get("derived_morphology")
    )
    severity = float_or_none(first_value(data, SEVERITY_KEYS))
    if severity is None:
        severity = float_or_none(descriptor_stats.get("derived_severity"))
    annotation_type = optional_text(data.get("annotation_type")) or "native_ground_truth"
    wm811k_extra = _wm811k_extra(data, raw_pattern=raw_pattern, annotation_type=annotation_type)

    return Evidence(
        case_id=case_id,
        dataset="wafer",
        source=source_value(data.get("source"), "image"),
        object="wafer",
        anomaly_type=anomaly_type,
        location=location,
        morphology=morphology,
        severity=severity,
        confidence=confidence,
        timestamp=optional_text(data.get("timestamp")),
        raw_evidence=RawEvidence(
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(
                data,
                known_keys=KNOWN_KEYS,
                required={
                    "wm811k": wm811k_extra,
                    "descriptor_stats": descriptor_stats,
                    **_path_extra(data),
                },
            ),
        ),
        observations=_wm811k_observations(
            case_id,
            anomaly_type,
            location,
            morphology,
            severity,
            confidence,
            pattern_source=_pattern_source(data),
            location_source=(
                "adapter:wm811k"
                if first_value(data, LOCATION_KEYS) is not None
                else "wafer_map_descriptor"
            ),
            morphology_source=(
                "adapter:wm811k"
                if first_value(data, MORPHOLOGY_KEYS) is not None
                else "wafer_map_descriptor"
            ),
            severity_source=(
                "adapter:wm811k"
                if first_value(data, SEVERITY_KEYS) is not None
                else "wafer_map_descriptor"
            ),
        ),
        adapter=adapter_metadata(
            "wm811k",
            metadata={
                "source_dataset": "wm811k",
                "schema_dataset": "wafer",
                "annotation_type": annotation_type,
            },
        ),
    )


def from_wm811k_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for WM811K record conversion."""
    return evidence_from_wm811k_record(record, **overrides)


def is_wm811k_record(record: Mapping[str, Any]) -> bool:
    """Return whether a wafer record explicitly requests WM811K semantics."""
    adapter_name = optional_text(record.get("adapter") or record.get("adapter_name"))
    source_dataset = optional_text(record.get("source_dataset"))
    if adapter_name and adapter_name.lower() == "wm811k":
        return True
    return source_dataset is not None and source_dataset.lower() in {"wm811k", "wm-811k"}


def _wm811k_observations(
    case_id: str,
    anomaly_type: str,
    location: str | None,
    morphology: str | None,
    severity: float | None,
    confidence: float | None,
    *,
    pattern_source: str,
    location_source: str,
    morphology_source: str,
    severity_source: str,
) -> list[EvidenceObservation]:
    observations: list[EvidenceObservation] = [
        make_observation(
            case_id,
            "object",
            "wafer",
            confidence=confidence,
            source_ref="adapter:wm811k",
            raw_ref="object",
        ),
        make_observation(
            case_id,
            "anomaly_type",
            anomaly_type,
            confidence=confidence,
            source_ref=pattern_source,
            raw_ref="raw_evidence.extra.wm811k.original_pattern",
        ),
        make_observation(
            case_id,
            "spatial_pattern",
            anomaly_type,
            confidence=confidence,
            source_ref=pattern_source,
            raw_ref="raw_evidence.extra.wm811k.original_pattern",
        ),
    ]
    if location:
        observations.append(
            make_observation(
                case_id,
                "location",
                location,
                confidence=confidence,
                source_ref=location_source,
                raw_ref=(
                    "location"
                    if location_source == "adapter:wm811k"
                    else "raw_evidence.extra.descriptor_stats"
                ),
            )
        )
    if morphology:
        observations.append(
            make_observation(
                case_id,
                "morphology",
                morphology,
                confidence=confidence,
                source_ref=morphology_source,
                raw_ref=(
                    "morphology"
                    if morphology_source == "adapter:wm811k"
                    else "raw_evidence.extra.descriptor_stats"
                ),
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
                source_ref=severity_source,
                raw_ref=(
                    "severity"
                    if severity_source == "adapter:wm811k"
                    else "raw_evidence.extra.descriptor_stats.defect_density"
                ),
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
                source_ref=_confidence_source(),
                raw_ref="confidence",
            )
        )
    return observations


def _wm811k_extra(
    data: Mapping[str, Any],
    *,
    raw_pattern: str,
    annotation_type: str,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "source_dataset": "wm811k",
        "original_pattern": raw_pattern,
        "annotation_type": annotation_type,
    }
    for key in ("wafer_id", "lot_id", "batch_id", "map_shape", "wafer_map_path"):
        value = data.get(key)
        if value is not None:
            extra[key] = value
    if "wafer_map" in data:
        extra["wafer_map"] = data["wafer_map"]
    return extra


def _path_extra(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in PATH_KEYS if key in data and data[key] is not None}


def _pattern_source(data: Mapping[str, Any]) -> str:
    if data.get("predicted_pattern") is not None:
        return "classifier_output"
    if data.get("failure_pattern") is not None or data.get("label") is not None:
        return "dataset_label"
    return "adapter:wm811k"


def _confidence_source() -> str:
    return "classifier_output"


def _canonical_pattern(value: Any) -> str:
    text = text_value(value, "unknown").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "near_full": "nearfull",
        "nearfull": "nearfull",
        "edge_loc": "edge_loc",
        "edgeloc": "edge_loc",
        "edge_ring": "edge_ring",
        "edgering": "edge_ring",
        "centre": "center",
    }
    return aliases.get(text, text)
