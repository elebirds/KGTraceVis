"""Deterministic helpers for mask-derived visual evidence features."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def normalize_mask_stats(
    stats: Mapping[str, Any] | None = None,
    *,
    bbox: Sequence[Any] | None = None,
    centroid: Sequence[Any] | Mapping[str, Any] | None = None,
    area: Any | None = None,
    area_ratio: Any | None = None,
    eccentricity: Any | None = None,
    component_count: Any | None = None,
    image_shape: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Normalize precomputed mask geometry into a small deterministic stats dict."""
    normalized = dict(stats or {})
    _set_if_present(normalized, "bbox", bbox)
    _set_if_present(normalized, "centroid", centroid)
    _set_float_if_present(normalized, "area", area)
    _set_float_if_present(normalized, "area_ratio", area_ratio)
    _set_float_if_present(normalized, "eccentricity", eccentricity)
    _set_int_if_present(normalized, "component_count", component_count)
    _set_if_present(normalized, "image_shape", image_shape)

    if "area_ratio" not in normalized and "area" in normalized:
        total_pixels = _total_pixels(normalized.get("image_shape"))
        if total_pixels:
            normalized["area_ratio"] = _clamp(float(normalized["area"]) / total_pixels)

    if "aspect_ratio" not in normalized:
        aspect_ratio = _aspect_ratio(normalized.get("bbox"))
        if aspect_ratio is not None:
            normalized["aspect_ratio"] = aspect_ratio

    if "centroid_norm" not in normalized:
        centroid_norm = _normalized_centroid(
            normalized.get("centroid"),
            normalized.get("image_shape"),
        )
        if centroid_norm is not None:
            normalized["centroid_norm"] = centroid_norm

    return normalized


def derive_mask_severity(stats: Mapping[str, Any]) -> float | None:
    """Derive numeric severity from normalized mask area ratio when available."""
    area_ratio = _float_or_none(stats.get("area_ratio"))
    if area_ratio is not None:
        return _clamp(area_ratio)
    return None


def derive_mask_location(stats: Mapping[str, Any]) -> str | None:
    """Derive a coarse visual location from mask centroid or explicit geometry stats."""
    explicit = _text_or_none(stats.get("location") or stats.get("zone") or stats.get("region"))
    if explicit:
        return explicit

    centroid_norm = _centroid_pair(stats.get("centroid_norm"))
    if centroid_norm is None:
        centroid_norm = _normalized_centroid(stats.get("centroid"), stats.get("image_shape"))
    if centroid_norm is None:
        return None

    x_norm, y_norm = centroid_norm
    if x_norm <= 0.2 or x_norm >= 0.8 or y_norm <= 0.2 or y_norm >= 0.8:
        return "edge"
    return "surface"


def derive_mask_morphology(stats: Mapping[str, Any]) -> str | None:
    """Derive a coarse morphology label from deterministic mask geometry stats."""
    explicit = _text_or_none(stats.get("morphology") or stats.get("shape") or stats.get("pattern"))
    if explicit:
        return explicit

    eccentricity = _float_or_none(stats.get("eccentricity"))
    aspect_ratio = _float_or_none(stats.get("aspect_ratio"))
    component_count = _int_or_none(stats.get("component_count"))
    area_ratio = _float_or_none(stats.get("area_ratio"))

    if eccentricity is not None and eccentricity >= 0.8:
        return "linear"
    if aspect_ratio is not None and aspect_ratio >= 3.0:
        return "linear"
    if component_count is not None and component_count >= 4:
        return "scattered"
    if area_ratio is not None and area_ratio >= 0.35:
        return "dense"
    if area_ratio is not None or component_count is not None:
        return "spot"
    return None


def summarize_mask_features(
    stats: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Return normalized mask stats plus derived location, morphology, and severity."""
    normalized = normalize_mask_stats(stats, **overrides)
    derived: dict[str, Any] = {"mask_stats": normalized}
    location = derive_mask_location(normalized)
    morphology = derive_mask_morphology(normalized)
    severity = derive_mask_severity(normalized)
    if location is not None:
        derived["location"] = location
    if morphology is not None:
        derived["morphology"] = morphology
    if severity is not None:
        derived["severity"] = severity
    return derived


def _set_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None and key not in target:
        target[key] = value


def _set_float_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target or value is None:
        return
    number = _float_or_none(value)
    if number is not None:
        target[key] = number


def _set_int_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target or value is None:
        return
    number = _int_or_none(value)
    if number is not None:
        target[key] = number


def _aspect_ratio(bbox: Any) -> float | None:
    if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)) or len(bbox) != 4:
        return None
    values: list[float] = []
    for value in bbox:
        number = _float_or_none(value)
        if number is None:
            return None
        values.append(number)
    x1, y1, x2, y2 = values
    width = abs(x2 - x1)
    height = abs(y2 - y1)
    shortest = min(width, height)
    if shortest <= 0:
        return None
    return max(width, height) / shortest


def _normalized_centroid(centroid: Any, image_shape: Any) -> tuple[float, float] | None:
    pair = _centroid_pair(centroid)
    if pair is None:
        return None
    x_value, y_value = pair
    if 0 <= x_value <= 1 and 0 <= y_value <= 1:
        return (x_value, y_value)

    shape = _shape_pair(image_shape)
    if shape is None:
        return None
    height, width = shape
    if width <= 1 or height <= 1:
        return None
    return (_clamp(x_value / (width - 1)), _clamp(y_value / (height - 1)))


def _centroid_pair(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        x_value = _float_or_none(value.get("x") or value.get("col") or value.get("column"))
        y_value = _float_or_none(value.get("y") or value.get("row"))
        if x_value is None or y_value is None:
            return None
        return (x_value, y_value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        x_value = _float_or_none(value[0])
        y_value = _float_or_none(value[1])
        if x_value is None or y_value is None:
            return None
        return (x_value, y_value)
    return None


def _shape_pair(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        height = _float_or_none(value.get("height") or value.get("rows"))
        width = _float_or_none(value.get("width") or value.get("cols") or value.get("columns"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        height = _float_or_none(value[0])
        width = _float_or_none(value[1])
    else:
        return None
    if height is None or width is None:
        return None
    return (height, width)


def _total_pixels(image_shape: Any) -> float | None:
    pair = _shape_pair(image_shape)
    if pair is None:
        return None
    height, width = pair
    total = height * width
    return total if total > 0 else None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
