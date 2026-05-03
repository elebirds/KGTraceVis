"""Deterministic helpers for wafer-map spatial descriptor features."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from math import sqrt
from typing import Any


def normalize_wafer_map_features(
    stats: Mapping[str, Any] | None = None,
    *,
    wafer_map: Sequence[Sequence[Any]] | None = None,
    pattern: str | None = None,
    die_count: Any | None = None,
    failed_die_count: Any | None = None,
    defect_density: Any | None = None,
    map_shape: Sequence[Any] | Mapping[str, Any] | None = None,
    zone: Any | None = None,
    morphology: Any | None = None,
) -> dict[str, Any]:
    """Normalize precomputed or tiny-array wafer-map descriptors."""
    normalized = dict(stats or {})
    _set_if_present(normalized, "pattern", pattern)
    _set_text_if_present(normalized, "zone", zone)
    _set_text_if_present(normalized, "morphology", morphology)
    _set_int_if_present(normalized, "die_count", die_count)
    _set_int_if_present(normalized, "failed_die_count", failed_die_count)
    _set_float_if_present(normalized, "defect_density", defect_density)
    _set_shape_if_present(normalized, "map_shape", map_shape)

    if wafer_map is not None:
        normalized.update(
            {
                key: value
                for key, value in _stats_from_wafer_map(wafer_map).items()
                if key not in normalized
            }
        )

    if "defect_density" not in normalized:
        failed = _int_or_none(normalized.get("failed_die_count"))
        total = _int_or_none(normalized.get("die_count"))
        if failed is not None and total:
            normalized["defect_density"] = _clamp(failed / total)

    location = derive_wafer_location(normalized)
    derived_morphology = derive_wafer_morphology(normalized)
    severity = derive_wafer_severity(normalized)
    if location is not None:
        normalized["derived_location"] = location
    if derived_morphology is not None:
        normalized["derived_morphology"] = derived_morphology
    if severity is not None:
        normalized["derived_severity"] = severity
    return normalized


def derive_wafer_severity(stats: Mapping[str, Any]) -> float | None:
    """Derive numeric wafer severity from defect density."""
    density = _float_or_none(stats.get("defect_density"))
    if density is not None:
        return _clamp(density)
    return None


def derive_wafer_location(stats: Mapping[str, Any]) -> str | None:
    """Derive a coarse wafer location/zone from descriptors."""
    explicit = _text_or_none(stats.get("zone") or stats.get("location"))
    if explicit:
        return explicit

    pattern = _canonical_pattern(stats.get("pattern"))
    if pattern == "nearfull":
        return "wafer_surface"
    if pattern == "center":
        return "center"
    if pattern in {"edge_loc", "edge_ring"}:
        return "edge"
    if pattern == "loc":
        return "local"

    density = _float_or_none(stats.get("defect_density"))
    if density is not None and density >= 0.45:
        return "wafer_surface"

    centroid = _centroid_pair(stats.get("centroid_norm"))
    if centroid is None:
        return None
    x_norm, y_norm = centroid
    radial = _radial_distance(x_norm, y_norm)
    if radial >= 0.6:
        return "edge"
    if radial <= 0.25:
        return "center"
    return "local"


def derive_wafer_morphology(stats: Mapping[str, Any]) -> str | None:
    """Derive a coarse wafer morphology from pattern and spatial descriptors."""
    explicit = _text_or_none(stats.get("morphology"))
    if explicit:
        return explicit

    pattern = _canonical_pattern(stats.get("pattern"))
    if pattern == "nearfull":
        return "dense_particles"
    if pattern in {"edge_ring", "donut"}:
        return "ring"
    if pattern == "scratch":
        return "linear"
    if pattern == "random":
        return "scattered"
    if pattern in {"center", "loc", "edge_loc"}:
        return "clustered"

    density = _float_or_none(stats.get("defect_density"))
    component_count = _int_or_none(stats.get("component_count"))
    if density is not None and density >= 0.45:
        return "dense_particles"
    if component_count is not None and component_count >= 4:
        return "scattered"
    if component_count is not None and component_count <= 2:
        return "clustered"
    return None


def _stats_from_wafer_map(wafer_map: Sequence[Sequence[Any]]) -> dict[str, Any]:
    rows = [
        list(row)
        for row in wafer_map
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes))
    ]
    row_count = len(rows)
    col_count = max((len(row) for row in rows), default=0)
    die_count = sum(len(row) for row in rows)
    failed_positions = _failed_positions(rows)
    failed_count = len(failed_positions)
    stats: dict[str, Any] = {
        "map_shape": [row_count, col_count],
        "die_count": die_count,
        "failed_die_count": failed_count,
        "defect_density": _clamp(failed_count / die_count) if die_count else 0.0,
        "component_count": _component_count(failed_positions),
    }
    if failed_positions and row_count > 1 and col_count > 1:
        row_mean = sum(row for row, _col in failed_positions) / failed_count
        col_mean = sum(col for _row, col in failed_positions) / failed_count
        x_norm = _clamp(col_mean / (col_count - 1))
        y_norm = _clamp(row_mean / (row_count - 1))
        stats["centroid_norm"] = [x_norm, y_norm]
        stats["radial_mean"] = sum(
            _radial_distance(col / (col_count - 1), row / (row_count - 1))
            for row, col in failed_positions
        ) / failed_count
    return stats


def _failed_positions(rows: Sequence[Sequence[Any]]) -> set[tuple[int, int]]:
    numeric_values = [
        number
        for row in rows
        for value in row
        if (number := _float_or_none(value)) is not None
    ]
    has_explicit_failed_value = any(value > 1 for value in numeric_values)
    positions: set[tuple[int, int]] = set()
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            number = _float_or_none(value)
            if number is None:
                continue
            if (has_explicit_failed_value and number > 1) or (
                not has_explicit_failed_value and number > 0
            ):
                positions.add((row_index, col_index))
    return positions


def _component_count(positions: set[tuple[int, int]]) -> int:
    remaining = set(positions)
    count = 0
    while remaining:
        count += 1
        start = remaining.pop()
        queue: deque[tuple[int, int]] = deque([start])
        while queue:
            row, col = queue.popleft()
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return count


def _canonical_pattern(value: Any) -> str | None:
    text = _text_or_none(value)
    if text is None:
        return None
    token = text.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "near_full": "nearfull",
        "nearfull": "nearfull",
        "edge_loc": "edge_loc",
        "edgeloc": "edge_loc",
        "edge_ring": "edge_ring",
        "edgering": "edge_ring",
        "donut": "donut",
        "center": "center",
        "centre": "center",
        "loc": "loc",
        "local": "loc",
        "scratch": "scratch",
        "random": "random",
    }
    return aliases.get(token, token)


def _set_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None and key not in target:
        target[key] = value


def _set_text_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target:
        return
    text = _text_or_none(value)
    if text is not None:
        target[key] = text


def _set_float_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target:
        return
    number = _float_or_none(value)
    if number is not None:
        target[key] = number


def _set_int_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target:
        return
    number = _int_or_none(value)
    if number is not None:
        target[key] = number


def _set_shape_if_present(target: dict[str, Any], key: str, value: Any | None) -> None:
    if key in target:
        return
    if isinstance(value, Mapping):
        rows = _int_or_none(value.get("rows") or value.get("height"))
        cols = _int_or_none(value.get("cols") or value.get("columns") or value.get("width"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        rows = _int_or_none(value[0])
        cols = _int_or_none(value[1])
    else:
        return
    if rows is not None and cols is not None:
        target[key] = [rows, cols]


def _centroid_pair(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        x_value = _float_or_none(value[0])
        y_value = _float_or_none(value[1])
        if x_value is not None and y_value is not None:
            return (x_value, y_value)
    if isinstance(value, Mapping):
        x_value = _float_or_none(value.get("x") or value.get("col") or value.get("column"))
        y_value = _float_or_none(value.get("y") or value.get("row"))
        if x_value is not None and y_value is not None:
            return (x_value, y_value)
    return None


def _radial_distance(x_norm: float, y_norm: float) -> float:
    return sqrt((x_norm - 0.5) ** 2 + (y_norm - 0.5) ** 2) / sqrt(0.5)


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
