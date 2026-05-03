"""DS-MVTec / MVTec record adapter."""

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
from kgtracevis.mask.mask_feature_extractor import summarize_mask_features
from kgtracevis.schema.evidence_schema import Evidence, EvidenceObservation, RawEvidence

CASE_KEYS = ("case_id", "sample_id", "image_id", "record_id", "id")
OBJECT_KEYS = ("object", "object_name", "category", "class_name", "product")
ANOMALY_KEYS = ("anomaly_type", "defect_type", "defect", "label", "class_label")
LOCATION_KEYS = ("location", "region", "surface")
MORPHOLOGY_KEYS = ("morphology", "shape", "pattern")
SEVERITY_KEYS = ("severity", "anomaly_score")
CONFIDENCE_KEYS = ("confidence", "score")
IMAGE_REGION_KEYS = ("image_region", "region_id", "mask_region")
HEATMAP_KEYS = ("heatmap_path", "heatmap")
DESCRIPTION_KEYS = ("description", "caption")
PATH_KEYS = ("image_path", "mask_path", "heatmap_path", "segmentation_path", "gt_mask_path")
GEOMETRY_KEYS = (
    "mask_stats",
    "geometry",
    "bbox",
    "bounding_box",
    "polygon",
    "area",
    "area_ratio",
    "centroid",
    "eccentricity",
    "component_count",
    "image_shape",
)
DETECTOR_KEYS = (
    "detector",
    "detector_metadata",
    "model_name",
    "model_version",
    "pred_label",
    "pred_score",
    "detector_score",
)
ROOT_CAUSE_KEYS = (
    "root_cause",
    "root_causes",
    "candidate_root_cause",
    "candidate_root_causes",
    "ranked_causes",
    "top_k_paths",
)
DETECTOR_CONFIDENCE_KEYS = (*CONFIDENCE_KEYS, "pred_score", "detector_score", "anomaly_score")

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
    *IMAGE_REGION_KEYS,
    *HEATMAP_KEYS,
    *DESCRIPTION_KEYS,
    *PATH_KEYS,
    *GEOMETRY_KEYS,
    *DETECTOR_KEYS,
    *ROOT_CAUSE_KEYS,
}


def evidence_from_mvtec_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified evidence from an MVTec or DS-MVTec-style record."""
    data = merged_record(record, overrides)
    case_id = text_value(first_value(data, CASE_KEYS), "mvtec_unknown")
    object_name = text_value(first_value(data, OBJECT_KEYS), "unknown")
    anomaly_type = text_value(first_value(data, ANOMALY_KEYS), "unknown")
    feature_summary = _mask_feature_summary(data)
    mask_stats = feature_summary.get("mask_stats")

    location = optional_text(first_value(data, LOCATION_KEYS)) or optional_text(
        feature_summary.get("location")
    )
    morphology = optional_text(first_value(data, MORPHOLOGY_KEYS)) or optional_text(
        feature_summary.get("morphology")
    )
    severity = float_or_none(first_value(data, SEVERITY_KEYS))
    if severity is None:
        severity = float_or_none(feature_summary.get("severity"))
    detector_extra = _detector_extra(data)
    confidence = float_or_none(first_value(data, DETECTOR_CONFIDENCE_KEYS))
    if confidence is None:
        confidence = float_or_none(
            first_value(detector_extra, ("confidence", "score", "pred_score", "detector_score"))
        )
    path_extra = {
        key: data[key]
        for key in (*PATH_KEYS, *GEOMETRY_KEYS)
        if key in data and data[key] is not None
    }
    if isinstance(mask_stats, Mapping) and mask_stats:
        path_extra["mask_stats"] = mask_stats
    if detector_extra:
        path_extra["detector"] = detector_extra
    heatmap_path = optional_text(first_value(data, HEATMAP_KEYS))
    if heatmap_path is not None:
        path_extra["heatmap_path"] = heatmap_path
    location_source = (
        "adapter:mvtec" if first_value(data, LOCATION_KEYS) is not None else "mask_geometry"
    )
    morphology_source = (
        "adapter:mvtec" if first_value(data, MORPHOLOGY_KEYS) is not None else "mask_geometry"
    )
    severity_source = (
        "adapter:mvtec" if first_value(data, SEVERITY_KEYS) is not None else "mask_geometry"
    )
    confidence_source = (
        "adapter:mvtec" if first_value(data, CONFIDENCE_KEYS) is not None else "detector_output"
    )

    return Evidence(
        case_id=case_id,
        dataset="mvtec",
        source=source_value(data.get("source"), "image"),
        object=object_name,
        anomaly_type=anomaly_type,
        location=location,
        morphology=morphology,
        severity=severity,
        confidence=confidence,
        timestamp=optional_text(data.get("timestamp")),
        raw_evidence=RawEvidence(
            image_region=optional_text(first_value(data, IMAGE_REGION_KEYS)),
            heatmap_path=heatmap_path,
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(data, known_keys=KNOWN_KEYS, required=path_extra),
        ),
        observations=_mvtec_observations(
            case_id,
            object_name,
            anomaly_type,
            location,
            morphology,
            severity,
            confidence,
            location_source=location_source,
            morphology_source=morphology_source,
            severity_source=severity_source,
            confidence_source=confidence_source,
        ),
        adapter=adapter_metadata("mvtec"),
    )


def _mvtec_observations(
    case_id: str,
    object_name: str,
    anomaly_type: str,
    location: str | None,
    morphology: str | None,
    severity: float | None,
    confidence: float | None,
    *,
    location_source: str = "adapter:mvtec",
    morphology_source: str = "adapter:mvtec",
    severity_source: str = "adapter:mvtec",
    confidence_source: str = "adapter:mvtec",
) -> list[EvidenceObservation]:
    observations: list[EvidenceObservation] = [
        make_observation(
            case_id,
            "object",
            object_name,
            confidence=confidence,
            source_ref="adapter:mvtec",
            raw_ref="object",
        ),
        make_observation(
            case_id,
            "anomaly_type",
            anomaly_type,
            confidence=confidence,
            source_ref="adapter:mvtec",
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
                source_ref=location_source,
                raw_ref=(
                    "location"
                    if location_source == "adapter:mvtec"
                    else "raw_evidence.extra.mask_stats"
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
                    if morphology_source == "adapter:mvtec"
                    else "raw_evidence.extra.mask_stats"
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
                    if severity_source == "adapter:mvtec"
                    else "raw_evidence.extra.mask_stats.area_ratio"
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
                source_ref=confidence_source,
                raw_ref=(
                    "confidence"
                    if confidence_source == "adapter:mvtec"
                    else "raw_evidence.extra.detector"
                ),
            )
        )
    return observations


def _mask_feature_summary(data: Mapping[str, Any]) -> dict[str, Any]:
    geometry = data.get("geometry")
    geometry_data = dict(geometry) if isinstance(geometry, Mapping) else {}
    mask_stats = data.get("mask_stats")
    stats = mask_stats if isinstance(mask_stats, Mapping) else None
    return summarize_mask_features(
        stats,
        bbox=first_value(data, ("bbox", "bounding_box"), geometry_data.get("bbox")),
        centroid=first_value(data, ("centroid",), geometry_data.get("centroid")),
        area=first_value(data, ("area",), geometry_data.get("area")),
        area_ratio=first_value(data, ("area_ratio",), geometry_data.get("area_ratio")),
        eccentricity=first_value(data, ("eccentricity",), geometry_data.get("eccentricity")),
        component_count=first_value(
            data,
            ("component_count",),
            geometry_data.get("component_count"),
        ),
        image_shape=first_value(data, ("image_shape",), geometry_data.get("image_shape")),
    )


def _detector_extra(data: Mapping[str, Any]) -> dict[str, Any]:
    detector = data.get("detector") or data.get("detector_metadata")
    detector_extra = dict(detector) if isinstance(detector, Mapping) else {}
    for key in DETECTOR_KEYS:
        if key in {"detector", "detector_metadata"}:
            continue
        value = data.get(key)
        if value is not None:
            detector_extra[key] = value
    return detector_extra


def evidence_from_ds_mvtec_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified evidence from a DS-MVTec-style record."""
    return evidence_from_mvtec_record(record, **overrides)


def from_mvtec_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for MVTec record conversion."""
    return evidence_from_mvtec_record(record, **overrides)


def from_ds_mvtec_record(record: Mapping[str, Any] | None = None, **overrides: Any) -> Evidence:
    """Backward-friendly alias for DS-MVTec record conversion."""
    return evidence_from_ds_mvtec_record(record, **overrides)
