"""DS-MVTec / MVTec record adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kgtracevis.adapters._common import (
    copied_extra,
    first_value,
    float_or_none,
    merged_record,
    optional_text,
    source_value,
    text_value,
)
from kgtracevis.schema.evidence_schema import Evidence, RawEvidence

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
GEOMETRY_KEYS = ("bbox", "bounding_box", "polygon", "area")

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
}


def evidence_from_mvtec_record(
    record: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> Evidence:
    """Create unified evidence from an MVTec or DS-MVTec-style record."""
    data = merged_record(record, overrides)
    path_extra = {
        key: data[key]
        for key in (*PATH_KEYS, *GEOMETRY_KEYS)
        if key in data and data[key] is not None
    }
    heatmap_path = optional_text(first_value(data, HEATMAP_KEYS))
    if heatmap_path is not None:
        path_extra["heatmap_path"] = heatmap_path

    return Evidence(
        case_id=text_value(first_value(data, CASE_KEYS), "mvtec_unknown"),
        dataset="mvtec",
        source=source_value(data.get("source"), "image"),
        object=text_value(first_value(data, OBJECT_KEYS), "unknown"),
        anomaly_type=text_value(first_value(data, ANOMALY_KEYS), "unknown"),
        location=optional_text(first_value(data, LOCATION_KEYS)),
        morphology=optional_text(first_value(data, MORPHOLOGY_KEYS)),
        severity=float_or_none(first_value(data, SEVERITY_KEYS)),
        confidence=float_or_none(first_value(data, CONFIDENCE_KEYS)),
        timestamp=optional_text(data.get("timestamp")),
        raw_evidence=RawEvidence(
            image_region=optional_text(first_value(data, IMAGE_REGION_KEYS)),
            heatmap_path=heatmap_path,
            description=optional_text(first_value(data, DESCRIPTION_KEYS)),
            extra=copied_extra(data, known_keys=KNOWN_KEYS, required=path_extra),
        ),
    )


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
